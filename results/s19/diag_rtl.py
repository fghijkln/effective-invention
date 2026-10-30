import sys, json
sys.path[:0] = ['.', 'tests']
from omega import progs, fabric, rtl
import test_mempress as tm
name, N, W, H = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]); seed = int(sys.argv[5])
book = progs.book(name, N)
cells = tuple((x, y) for x in range(W) for y in range(H) if (x, y) != (W - 1, H - 1))
r = rtl.run(book, W, H, img=tm.ballast_img(book, W, H, 1024, *tm.GKEEP, cells), seed=seed, jitter=30, maxcycles=int(sys.argv[6]), timeout=1200)
print("rto", fabric.RTO, "rgrad", fabric.RGRAD, "status", r["status"], "cycles", r["cycles"], "inter", r["interactions"], "msgs", r["msgs"])
for y in range(H):
    print(" ".join(f"{r['cells'][(x,y)]['free_nodes']:4d}/{r['cells'][(x,y)]['free_vars']:<4d}" for x in range(W)))
print("parks")
for y in range(H):
    print(" ".join(f"{r['cells'][(x,y)]['park']:6d}" for x in range(W)))
print("interactions")
for y in range(H):
    print(" ".join(f"{r['cells'][(x,y)]['interactions']:6d}" for x in range(W)))
