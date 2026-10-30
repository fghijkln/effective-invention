"""Step 18: retry-slot timeout on the RTL under global memory pressure (the test_mempress GLOBAL cases + 3 bigger).
usage: OMEGA_RTO=r rto18_rtl.py seeds [case-index ...]   -> one jsonl line per run on stdout"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..")); sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tests"))
from omega import progs, fabric, rtl, semantic
import test_mempress as tm
CASES = tm.GLOBAL + [("fib", 12, 6, 6), ("qsort", 15, 6, 6), ("treesum", 7, 8, 8)]
idx = [int(a) for a in sys.argv[2:]] or range(len(CASES))
for i in idx:
    name, N, W, H = CASES[i]
    book = progs.book(name, N); want = progs.expected(name, N)
    ref = semantic.result(book, fuel=10**8)
    cells = tuple((x, y) for x in range(W) for y in range(H) if (x, y) != (W - 1, H - 1))
    for s in range(1, int(sys.argv[1]) + 1):
        r = rtl.run(book, W, H, img=tm.ballast_img(book, W, H, 1024, *tm.GKEEP, cells), seed=s, jitter=30, maxcycles=2_000_000, timeout=600)
        ok = r["status"] == 0 and r["readback"] == want and r["interactions"] == ref["interactions"]
        park = sum(c.get("park", 0) for c in r["cells"].values())
        print(json.dumps({"rto": fabric.RTO, "case": f"{name}({N}) {W}x{H}", "seed": s, "ok": ok, "cycles": r["cycles"],
                          "msgs": sum(r["msgs"].values()) if isinstance(r["msgs"], dict) else r["msgs"], "park": park}), flush=True)
