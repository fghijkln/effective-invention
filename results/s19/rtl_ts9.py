"""Step 19: treesum(9) 3x3 under global memory pressure on the RTL.  usage: OMEGA_RTO=r rtl_ts9.py s0 s1 [extra +args via OMEGA_XARGS]"""
import sys, os, json
sys.path[:0] = ['.', 'tests']
from omega import progs, fabric, rtl, semantic
import test_mempress as tm
name, N, W, H = "treesum", 9, 3, 3
book = progs.book(name, N); want = progs.expected(name, N); ref = semantic.result(book, fuel=10**8)
cells = tuple((x, y) for x in range(W) for y in range(H) if (x, y) != (W - 1, H - 1))
for s in range(int(sys.argv[1]), int(sys.argv[2]) + 1):
    r = rtl.run(book, W, H, img=tm.ballast_img(book, W, H, 1024, *tm.GKEEP, cells), seed=s, jitter=30, maxcycles=1_500_000, timeout=900)
    ok = r["status"] == 0 and r["readback"] == want and r["interactions"] == ref["interactions"]
    print(json.dumps({"rto": fabric.RTO, "x": os.environ.get("OMEGA_XARGS", ""), "seed": s, "ok": ok, "status": r["status"], "cycles": r["cycles"],
                      "interactions": r["interactions"]}), flush=True)
