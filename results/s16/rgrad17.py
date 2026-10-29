"""Step 17 probe (fabric model): room gradient vs round-robin escalation under global memory pressure.
usage: OMEGA_RGRAD=G rgrad17.py seeds  -- the 5 GLOBAL cases of tests/test_mempress.py (+ two bigger meshes)"""
import sys, os, statistics as S
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..")); sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tests"))
from omega import progs, fabric, semantic
import test_mempress as tm
seeds = range(1, int(sys.argv[1]) + 1)
CASES = tm.GLOBAL + [("fib", 12, 6, 6), ("qsort", 15, 6, 6), ("treesum", 7, 8, 8)]
for name, N, W, H in CASES:
    book = progs.book(name, N); want = progs.expected(name, N)
    cells = tuple((x, y) for x in range(W) for y in range(H) if (x, y) != (W - 1, H - 1))
    cyc, msg, hops = [], [], []
    for s in seeds:
        f = fabric.Fabric(book, W, H, seed=s, p_jitter=0.1, img=tm.ballast_img(book, W, H, 1024, *tm.GKEEP, cells)).run()
        assert f.readback() == want, (name, f.readback())
        r = f.report(); cyc.append(r["cycles"]); msg.append(sum(r["msgs"].values())); hops.append(f.hops)
    print(f"RGRAD={fabric.RGRAD} {name}({N}) {W}x{H}: cycles {S.mean(cyc):,.0f} (sd {S.stdev(cyc):,.0f})  msgs {S.mean(msg):,.0f}  hops {S.mean(hops):,.0f}", flush=True)
