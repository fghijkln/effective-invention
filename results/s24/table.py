"""Step 24 README table: B vs measured peaks (results/s24/eal.json from tests/test_eal.py --json; W from results/s24/worst.py).
Fills fabric peaks for rows that the test ran only on the RTL (same fabric_peak as the test)."""
import json, sys
sys.path[:0] = [".", "tests", "results/s24"]
import test_eal, worst
from omega import progs, semantic
from omega.ports import *
rows = json.load(open("results/s24/eal.json"))
f = lambda p: f"{p[0]:,} / {p[1]:,}"


def W(name, N):
    b = progs.book(name, N); net = worst.DNet(b); r = net.alloc_var(); net.instantiate(b.id("main"), mk(VAR, 0, r))
    n0 = len(net.nodes); net.normalize(None, 10**8, "lifo"); return n0 + worst.maxclosure(net.w, net.deps)


print("| program | B nodes / vars | causal W (nodes) | semantic depth first | semantic breadth first | fabric 1×1 | fabric 4×4 (whole mesh) | RTL 1×1 | B / RTL 1×1 peak (nodes, vars) | RTL 1×1 with exactly B slots |")
print("|---|---:|---:|---:|---:|---:|---:|---:|---:|---|")
for r in rows:
    if "rtl_1x1" not in r: continue
    b = progs.book(r["prog"], r["N"])
    for W_, H_, s in ((1, 1, 0), (4, 4, 9)):
        if f"fabric_{W_}x{H_}" not in r:
            pk = test_eal.fabric_peak(b, W_, H_, s); r[f"fabric_{W_}x{H_}"] = [pk["g_nodes"], pk["g_vars"]]
    rt, ab = r["rtl_1x1"], r["rtl_at_bound"]
    print(f"| {r['prog']}({r['N']}) | {f((r['B_nodes'], r['B_vars']))} | {W(r['prog'], r['N']):,} | {f(r['lifo'])} | {f(r['fifo'])} | "
          f"{f(r['fabric_1x1'])} | {f(r['fabric_4x4'])} | {f(rt)} | {r['B_nodes'] / rt[0]:.0f}×, {r['B_vars'] / rt[1]:.1f}× | "
          f"status {ab[3]} ({ab[2]:,} cycles, peak {f(ab)}) |", flush=True)
