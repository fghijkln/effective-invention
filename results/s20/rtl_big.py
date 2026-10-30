"""Step 20 (copy of results/s19/rtl_big.py + rsv): more seeds on the global-pressure cases (RTL).  usage: OMEGA_RTO=r OMEGA_RGRAD=g rtl_big.py s0 s1 [case-index ...]"""
import sys, os, json
sys.path[:0] = ['.', 'tests']
from omega import progs, fabric, rtl, semantic
import test_mempress as tm
CASES = tm.GLOBAL + [("fib", 12, 6, 6), ("qsort", 15, 6, 6), ("treesum", 7, 8, 8)]
idx = [int(a) for a in sys.argv[3:]] or range(len(CASES))
for i in idx:
    name, N, W, H = CASES[i]
    book = progs.book(name, N); want = progs.expected(name, N); ref = semantic.result(book, fuel=10**8)
    cells = tuple((x, y) for x in range(W) for y in range(H) if (x, y) != (W - 1, H - 1))
    for s in range(int(sys.argv[1]), int(sys.argv[2]) + 1):
        r = rtl.run(book, W, H, img=tm.ballast_img(book, W, H, 1024, *tm.GKEEP, cells), seed=s, jitter=30, maxcycles=400_000, timeout=1200)
        ok = r["status"] == 0 and r["readback"] == want and r["interactions"] == ref["interactions"]
        print(json.dumps({"rto": fabric.RTO, "rgrad": fabric.RGRAD, "rsv": fabric.RSV, "case": f"{name}({N}) {W}x{H}", "seed": s, "ok": ok, "status": r["status"],
                          "cycles": r["cycles"], "msgs": sum(r["msgs"].values()), "interactions": r["interactions"]}), flush=True)
