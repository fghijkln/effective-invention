"""Fanout repair for a Yosys liberty-mapped netlist (a stand-in for OpenROAD's repair_design, which is
not available here): every net with more than FANOUT sinks gets a buffer tree (BUF_X4 leaves, BUF_X8
above), so pre-layout STA measures logic depth rather than a single gate driving hundreds of pins.
The clock net and constant nets are left alone.

usage: buffer_nets.py IN.v OUT.v LIB [MEMLIB ...]
"""
import re, sys
from collections import defaultdict

FANOUT = 16


def lib_dirs(path):
    """cell -> {pin: direction} from a Liberty file (pins and buses)."""
    dirs, cell, pin = {}, None, None
    for line in open(path):
        m = re.match(r"\s*cell\s*\(\s*\"?([\w$\\]+)\"?\s*\)", line)
        if m:
            cell = m.group(1); dirs[cell] = {}
        m = re.match(r"\s*(?:pin|bus)\s*\(\s*\"?(\w+)\"?\s*\)", line)
        if m and cell:
            pin = m.group(1)
            d = re.search(r"direction\s*:\s*(\w+)", line)
            if d: dirs[cell][pin] = d.group(1)
            continue
        d = re.search(r"^\s*direction\s*:\s*(\w+)", line)
        if d and cell and pin and pin not in dirs[cell]:
            dirs[cell][pin] = d.group(1)
    return dirs


def split_top(s):
    out, depth, cur = [], 0, ""
    for ch in s:
        if ch == "{": depth += 1
        if ch == "}": depth -= 1
        if ch == "," and depth == 0:
            out.append(cur.strip()); cur = ""
        else:
            cur += ch
    if cur.strip(): out.append(cur.strip())
    return out


class Mod:
    def __init__(self, name):
        self.name, self.header, self.wires, self.insts, self.assigns = name, [], {}, [], []
        self.ports = {}


def term(st):
    """Terminate a statement; an escaped identifier needs whitespace before the ';'."""
    last = st.split()[-1] if st.split() else ""
    return st + (" ;" if "\\" in last else ";")


def parse(path):
    mods, cur, inst = {}, None, None
    text = open(path).read()
    for raw in text.split(";"):
        st = raw.strip()
        if not st or st.startswith("/*"):
            st = re.sub(r"/\*.*?\*/", "", st, flags=re.S).strip()
            if not st: continue
        m = re.match(r"module\s+([\w$\\]+)", st)
        if m:
            cur = Mod(m.group(1)); mods[cur.name] = cur; cur.header.append(term(st)); continue
        if st == "endmodule" or st.startswith("endmodule"):
            rest = st[len("endmodule"):].strip()
            cur = None
            if rest.startswith("module"):
                m = re.match(r"module\s+([\w$\\]+)", rest)
                cur = Mod(m.group(1)); mods[cur.name] = cur; cur.header.append(rest + ";")
            continue
        if cur is None: continue
        m = re.match(r"(input|output|inout|wire)\s+(?:\[(\d+):(\d+)\]\s+)?([\w$\\.\[\]]+(?:\s*,\s*[\w$\\.\[\]]+)*)$", st, re.S)
        if m:
            kind = m.group(1); hi = int(m.group(2)) if m.group(2) else None; lo = int(m.group(3)) if m.group(3) else None
            for n in [x.strip() for x in m.group(4).split(",")]:
                if kind == "wire": cur.wires[n] = (hi, lo)
                else: cur.ports[n] = kind; cur.wires.setdefault(n, (hi, lo))
            cur.header.append(term(st)); continue
        if st.startswith("assign"):
            cur.assigns.append(term(st)); continue
        m = re.match(r"([\w$\\]+)\s+(?:#\(.*?\)\s*)?([\w$\\.\[\]]+)\s*\((.*)\)$", st, re.S)
        if m:
            conns = {}
            for pm in re.finditer(r"\.(\w+)\s*\(((?:[^()]|\([^()]*\))*)\)", m.group(3), re.S):
                conns[pm.group(1)] = pm.group(2).strip()
            cur.insts.append([m.group(1), m.group(2), conns])
            continue
        cur.header.append(term(st))
    return mods


def bits(expr, mod):
    """expression -> list of bit names (MSB first); constants -> None entries."""
    expr = expr.strip()
    if not expr: return []
    if expr.startswith("{"):
        out = []
        for p in split_top(expr[1:-1]): out += bits(p, mod)
        return out
    m = re.match(r"(\d+)'[hbd]([0-9a-fA-FxXzZ]+)$", expr)
    if m: return [None] * int(m.group(1))
    m = re.match(r"(.+?)\s*\[(\d+):(\d+)\]$", expr)
    if m:
        n, hi, lo = m.group(1).strip(), int(m.group(2)), int(m.group(3))
        rng = range(hi, lo - 1, -1) if hi >= lo else range(hi, lo + 1)
        return [f"{n} [{i}]" for i in rng]
    m = re.match(r"(.+?)\s*\[(\d+)\]$", expr)
    if m: return [f"{m.group(1).strip()} [{m.group(2)}]"]
    w = mod.wires.get(expr)
    if w and w[0] is not None:
        hi, lo = w
        rng = range(hi, lo - 1, -1) if hi >= lo else range(hi, lo + 1)
        return [f"{expr} [{i}]" for i in rng]
    return [expr]


def vname(b):
    n, _, i = b.partition(" [")
    if n.startswith("\\"): n += " "          # an escaped identifier ends at whitespace
    return f"{n}[{i}" if i else n


def repair(mod, dirs, mods, clk="clk"):
    drivers, sinks = {}, defaultdict(list)
    for k, inst in enumerate(mod.insts):
        typ, name, conns = inst
        if typ in mods:
            pdir = {p: mods[typ].ports.get(p, "input") for p in conns}
        else:
            pdir = dirs.get(typ, {})
        inst.append({p: bits(e, mod) for p, e in conns.items()})
        for p, bl in inst[3].items():
            d = pdir.get(p, "input")
            for j, b in enumerate(bl):
                if b is None: continue
                if d == "output": drivers[b] = (k, p, j)
                else: sinks[b].append((k, p, j))
    nbuf, newwires = 0, []
    for net, sk in list(sinks.items()):
        if len(sk) <= FANOUT or net.split(" [")[0] == clk: continue
        drv = drivers.get(net)
        if drv and mod.insts[drv[0]][0].startswith("LOGIC"): continue
        level = sk
        while len(level) > FANOUT:
            nxt = []
            for c in range(0, len(level), FANOUT):
                nn = f"_fbuf{nbuf}_"; bn = f"_fb{nbuf}_"; nbuf += 1
                newwires.append(nn)
                for (k, p, j) in level[c:c + FANOUT]:
                    mod.insts[k][3][p][j] = nn
                mod.insts.append(["BUF_X4" if level is sk else "BUF_X8", bn, {}, {"A": [net], "Z": [nn]}])
                nxt.append((len(mod.insts) - 1, "A", 0))
            level = nxt
    return nbuf, newwires


def emit(mods, out):
    with open(out, "w") as f:
        for mod in mods.values():
            for h in mod.header: f.write(h + "\n")
            for w in getattr(mod, "newwires", []): f.write(f"  wire {w};\n")
            for a in mod.assigns: f.write("  " + a + "\n")
            for inst in mod.insts:
                typ, name, conns, bl = inst
                parts = []
                for p, b in bl.items():
                    if len(b) == 1 and b[0] is not None and conns.get(p, "").strip() and not conns[p].strip().startswith("{") and "[" not in conns[p] and mod.wires.get(conns[p].strip(), (None, None))[0] is None and b[0] == conns[p].strip():
                        parts.append(f".{p}({vname(b[0])})")
                    else:
                        parts.append(f".{p}({{{', '.join(vname(x) if x is not None else chr(49) + chr(39) + 'b0' for x in b)}}})")
                f.write(f"  {typ} {name} ({', '.join(parts)});\n")
            f.write("endmodule\n")


if __name__ == "__main__":
    src, dst = sys.argv[1], sys.argv[2]
    dirs = {}
    for lib in sys.argv[3:]: dirs.update(lib_dirs(lib))
    mods = parse(src)
    total = 0
    for mod in mods.values():
        n, nw = repair(mod, dirs, mods)
        mod.newwires = nw
        total += n
    emit(mods, dst)
    print(f"buffers inserted: {total}")
