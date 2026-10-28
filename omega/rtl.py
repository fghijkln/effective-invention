"""Verilator harness for the RTL mesh: build per configuration, write the memory image, run,
read the node/var RAM dumps back and read back the normal form."""
import os, subprocess, tempfile, shutil, hashlib
from .ports import *
from . import fabric

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RTL = ["rtl/omega_router.sv", "rtl/omega_cell.sv", "rtl/omega_mesh.sv"]
HDRS = ["rtl/omega_defs.svh", "rtl/omega_funcs.svh"]
BUILD = os.environ.get("OMEGA_BUILD", "/tmp/omega_build")
ENV_SH = os.path.expanduser("~/env.sh")


def _env():
    env = dict(os.environ)
    if os.path.exists(ENV_SH):
        out = subprocess.run(["bash", "-c", f"source {ENV_SH} && env"], capture_output=True, text=True).stdout
        for line in out.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                env[k] = v
    return env


_ENV = None


def build(W, H, slots=1024, qdepth=1024, romsz=4096, mut=0, quiet=True):
    global _ENV
    if _ENV is None:
        _ENV = _env()
    src_hash = hashlib.sha1(b"".join(open(os.path.join(ROOT, f), "rb").read() for f in RTL + ["tb/tb_mesh.cpp"])).hexdigest()[:10]
    name = f"v{W}x{H}_s{slots}_q{qdepth}_r{romsz}_m{mut:x}_{src_hash}"
    d = os.path.join(BUILD, name)
    exe = os.path.join(d, "vsim")
    if os.path.exists(exe):
        return exe
    os.makedirs(BUILD, exist_ok=True)
    cmd = ["verilator", "--cc", "--exe", "--build", "-j", "2", "-O3", "-Wno-fatal", "-Wno-WIDTH", "-Wno-UNUSED",
           "-Wno-MULTIDRIVEN", "-Irtl", "--top-module", "omega_mesh", f"-GW={W}", f"-GH={H}", f"-GSLOTS={slots}",
           f"-GQDEPTH={qdepth}", f"-GROMSZ={romsz}", f"-GMUT=256'h{mut:x}", "-Mdir", d, "-o", "vsim",
           "-CFLAGS", "-O1"] + [os.path.join(ROOT, f) for f in RTL + ["tb/tb_mesh.cpp"]]
    r = subprocess.run(cmd, cwd=ROOT, env=_ENV, capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(exe):
        raise RuntimeError("verilator build failed:\n" + r.stdout[-3000:] + r.stderr[-3000:])
    # keep only the binary (object files are large)
    for f in os.listdir(d):
        if f != "vsim":
            p = os.path.join(d, f)
            if os.path.isfile(p): os.remove(p)
    return exe


def _readhex(path, n):
    out = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("//"): continue
            out.append(int(line, 16))
    return out[:n] if n else out


def run(book, W, H, seed=1, jitter=0, stall=0, pmsg=128, slots=1024, qdepth=1024, romsz=4096,
        mut=0, maxcycles=20_000_000, keep=None, img=None, timeout=600, fi=0):
    exe = build(W, H, slots, qdepth, romsz, mut)
    img = img or fabric.Image(book, W, H, slots, qdepth)
    if len(img.rom) > romsz or len(img.dir) > 256:
        raise fabric.FabricError("book does not fit the ROM")
    tmp = keep or tempfile.mkdtemp(prefix="omg_")
    try:
        img.write_hex(tmp)
        r = subprocess.run([exe, f"+img={tmp}", f"+seed={seed}", f"+jitter={jitter}", f"+stall={stall}",
                            f"+pmsg={pmsg}", f"+maxcycles={maxcycles}", f"+fi={fi}"], capture_output=True, text=True, timeout=timeout)
        res = {}
        for line in r.stdout.splitlines():
            k, _, v = line.partition(" ")
            if v.strip().lstrip("-").isdigit(): res[k] = int(v)
        if "status" not in res:
            raise RuntimeError("simulator crashed: " + r.stdout[-2000:] + r.stderr[-2000:])
        nodes, vars_, cells, nown = {}, {}, {}, {}
        for x in range(W):
            for y in range(H):
                nm = _readhex(f"{tmp}/out_node_{x}_{y}.hex", slots)
                na = _readhex(f"{tmp}/out_nalloc_{x}_{y}.hex", slots)
                vm = _readhex(f"{tmp}/out_var_{x}_{y}.hex", slots)
                # v2 dump: node word {owner, aux2, aux1}, var word {owner, port}
                nodes[(x, y)] = [[w & M64, (w >> 64) & M64] if a else None for w, a in zip(nm, na)]
                vars_[(x, y)] = [w & M64 for w in vm]
                nown[(x, y)] = [w >> 128 for w in nm]
                st = {}
                with open(f"{tmp}/out_stats_{x}_{y}.txt") as f:
                    for line in f:
                        k, v = line.split()
                        st[k] = int(v)
                cells[(x, y)] = st
        res["cells"] = cells
        res["node_count"] = sum(sum(e is not None for e in t) for t in nodes.values())
        if res["status"] == 0:
            try:
                res["readback"] = fabric.readback_dump(book, nodes, vars_, img.root)
            except Exception as e:
                res["readback"] = f"ERROR {e}"
        else:
            res["readback"] = f"STATUS {res['status']} err {res.get('err')}"
        # owner capabilities: per-tenant results and the (reason, owner) trap set
        res["tenants"] = []
        for k, t in enumerate(img.tenants):
            if res["status"] == 0:
                try:
                    rb = fabric.readback_dump(book, nodes, vars_, img.roots[k])
                except Exception as e:
                    rb = f"ERROR {type(e).__name__}"
            else:
                rb = res["readback"]
            res["tenants"].append({"owner": t["owner"], "readback": rb,
                                   "nodes": sum(1 for c in nodes for s, e in enumerate(nodes[c])
                                                if e is not None and nown[c][s] == t["owner"])})
        res["traps"] = sorted({(b // 16 + 1, b % 16) for c in cells.values() for b in range(48) if c.get("trap_mask", 0) >> b & 1})
        res["trap_count"] = sum(c.get("traps", 0) for c in cells.values())
        res["trap_first"] = {k: (c["trap_reason"], c["trap_owner"], c["trap_addr"]) for k, c in cells.items() if c.get("traps")}
        res["msgs"] = {k: sum(c[k] for c in cells.values()) for k in ("msg_link", "msg_node", "msg_spawn")}
        busy = [c["busy"] for c in cells.values()]
        res["util"] = sum(busy) / (len(busy) * max(1, res.get("cycles", 1)))
        return res
    finally:
        if not keep:
            shutil.rmtree(tmp, ignore_errors=True)
