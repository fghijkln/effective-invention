# step 22: near-overfull global pressure for several programs: every cell keeps 8/8 free slots except the corner,
# which keeps K = ceil(f x the program's 1x1 peak) free slots.  ADM given in env.  Prints one json line per case.
import sys, os, json, math; sys.path[:0]=['.','tests']
import test_mempress as tm
from omega import progs, fabric
from omega.ports import mk, ERA, NONE
f_ = float(sys.argv[1]); seeds = range(1, int(sys.argv[2]) + 1); W, H = 3, 3
for name, N in [("fib", 12), ("qsort", 15), ("list", 20), ("sort", 10), ("higher", 30), ("treesum", 7), ("treesum_direct", 8)]:
    b = progs.book(name, N); want = progs.expected(name, N)
    f1 = fabric.Fabric(b, 1, 1, seed=1); bn = len(f1.cells[(0, 0)].nfree); bv = len(f1.cells[(0, 0)].vfree)
    pk = 0
    while not all(c.idle() for c in f1.cells.values()):
        f1.step(); c = f1.cells[(0, 0)]; pk = max(pk, bn - len(c.nfree), bv - len(c.vfree))
    K = math.ceil(f_ * pk) + 8
    stuck, cyc, wrong = [], [], 0
    for s in seeds:
        i = tm.ballast_img(b, W, H, 1024, 8, 8, tuple((x, y) for x in range(W) for y in range(H) if (x, y) != (W - 1, H - 1)))
        c = (W - 1, H - 1); fn = [t for t in range(1024) if i.nodes[c][t] is None]; fv = [t for t in range(1024) if i.vars[c][t] is None]
        for t in fn[K:]: i.nodes[c][t] = [mk(ERA), mk(ERA)]; i.nown[c][t] = 14
        for t in fv[K:]: i.vars[c][t] = mk(NONE); i.vown[c][t] = 14
        try:
            f = fabric.Fabric(b, W, H, seed=s, p_jitter=0.1, img=i).run(); cyc.append(f.cycles); wrong += f.readback() != want
        except Exception: stuck.append(s)
    print(json.dumps({"adm": fabric.ADM, "prog": f"{name}({N})", "peak1x1": pk, "K": K, "f": f_, "stuck": len(stuck), "n": len(seeds),
                      "wrong": wrong, "cycles": round(sum(cyc) / len(cyc)) if cyc else None, "seq": f1.cycles}), flush=True)
