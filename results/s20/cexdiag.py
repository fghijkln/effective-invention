# step 20 B: state of a stalled run (treesum(9) 3x3, corner keeps K/K free slots, default knobs)
import sys, collections; sys.path[:0]=['.','tests']
import test_mempress as tm
from omega import progs, fabric
from omega.ports import mk, ERA, NONE
K=int(sys.argv[1]); s=int(sys.argv[2]); book=progs.book("treesum",9)
i=tm.ballast_img(book,3,3,1024,8,8,tuple((x,y) for x in range(3) for y in range(3) if (x,y)!=(2,2)))
c=(2,2); fn=[t for t in range(1024) if i.nodes[c][t] is None]; fv=[t for t in range(1024) if i.vars[c][t] is None]
for t in fn[K:]: i.nodes[c][t]=[mk(ERA),mk(ERA)]; i.nown[c][t]=14
for t in fv[K:]: i.vars[c][t]=mk(NONE); i.vown[c][t]=14
f=fabric.Fabric(book,3,3,seed=s,p_jitter=0.1,img=i)
try: f.run(); print("finished", f.cycles)
except Exception as e: print("stopped:", e, "at cycle", f.cycles)
tot=sum(cc.st["interactions"] for cc in f.cells.values()); print("interactions", tot)
for y in range(3):
    print(" | ".join(f"free {len(f.cells[(x,y)].nfree):4d}/{len(f.cells[(x,y)].vfree):4d} q{len(f.cells[(x,y)].queue):3d} rs{int(f.cells[(x,y)].rs is not None)} ej{len(f.cells[(x,y)].eject)}" for x in range(3)))
kinds=collections.Counter()
for cc in f.cells.values():
    for t in list(cc.queue): kinds[t[0]]+=1
    if cc.rs: kinds["rs:"+str(cc.rs[0])]+=1
print("pending tasks by kind (0 LINK, 1 EXPAND, 2 SPAWN, 3 FWD; rs: = parked in the retry slot)", dict(kinds))
