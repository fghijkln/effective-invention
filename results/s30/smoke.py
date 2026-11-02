import sys; sys.setrecursionlimit(100000)
from omega import rtl, progs, joint, eal
for name, N, W, H in (("fib", 8, 2, 2), ("treesum", 4, 3, 3), ("sum", 50, 1, 1)):
    bk = progs.book(name, N); L = joint.loads(bk)
    r = rtl.run(bk, W, H, extra=[f"+tcert={L['atoms']}", "+pcert=3"], timeout=600)
    print(name, N, W, H, r["status"], r["readback"], {k: r.get(k) for k in ("tcert_viol", "tcert_peak", "tcert_cell", "tcert_slack", "cycles")}, "Q", L["Q"], flush=True)
