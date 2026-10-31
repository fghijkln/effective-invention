"""Step 23: smallest corner K (free node = var slots) with which treesum(9) finishes on a 1x1 RTL cell (bisection), per +ilr / mutant."""
import sys; sys.path[:0] = ['.', 'tests']
import test_mempress as tm
from omega import progs, rtl, fabric
b = progs.book("treesum", 9); want = progs.expected("treesum", 9)
def ok(K, mut):
    r = rtl.run(b, 1, 1, img=tm.ballast_img(b, 1, 1, 1024, K, K, ((0, 0),)), mut=mut, maxcycles=400_000)
    return r["status"] == 0 and r["readback"] == want
for spec in sys.argv[1:]:
    ilr, mut = (int(x, 0) for x in spec.split(":"))
    fabric.ILR = ilr
    lo, hi = 60, 600          # lo fails, hi passes
    assert not ok(lo, mut) and ok(hi, mut)
    while hi - lo > 1:
        m = (lo + hi) // 2
        if ok(m, mut): hi = m
        else: lo = m
    print(f"ilr={ilr} mut={mut:#x}: treesum(9) 1x1 needs {hi} free slots ({lo} stops)", flush=True)
