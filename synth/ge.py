"""Gate-equivalent (NAND2 = 1) estimate from a Yosys `stat` report of a generic-gate netlist
(after techmap + abc).  Uses the totals of the 'design hierarchy' section when present.
Weights are typical static-CMOS standard-cell ratios (NOT 0.67, NAND/NOR 1, AND/OR/ANDNOT/ORNOT
1.33, XOR/XNOR/MUX 2.33, flip-flop 4.33, enable/reset flip-flop 5.33); they are an estimate, not a
cell library.  Memories ($mem_v2) are reported separately in bits.
usage: ge.py STAT [STAT...]"""
import re, sys

W = {"$_NOT_": 0.67, "$_NAND_": 1, "$_NOR_": 1, "$_AND_": 1.33, "$_OR_": 1.33, "$_ANDNOT_": 1.33,
     "$_ORNOT_": 1.33, "$_XOR_": 2.33, "$_XNOR_": 2.33, "$_MUX_": 2.33, "$_DFF_P_": 4.33, "$_DFF_N_": 4.33}


def weight(c):
    if c in W: return W[c]
    if "DFF" in c: return 5.33
    if c.startswith("$_"): return 1.33
    return 0.0


def parse(path):
    txt = open(path).read()
    if "design hierarchy" in txt:
        txt = txt[txt.index("design hierarchy"):]
    counts = {}
    for m in re.finditer(r"^\s+(\d+)\s+(\$\S+)\s*$", txt, re.M):
        counts[m.group(2)] = counts.get(m.group(2), 0) + int(m.group(1))
    return counts


def summary(path):
    c = parse(path)
    cells = sum(v for k, v in c.items() if k.startswith("$_"))
    ffs = sum(v for k, v in c.items() if "DFF" in k)
    ge = sum(v * weight(k) for k, v in c.items())
    return dict(cells=cells, ffs=ffs, ge=ge, mems=c.get("$mem_v2", 0))


if __name__ == "__main__":
    for p in sys.argv[1:]:
        s = summary(p)
        print(f"{p}: {s['cells']:,} generic cells, {s['ffs']:,} flip-flops, {s['ge']:,.0f} GE (NAND2-eq), {s['mems']} memory macros")
