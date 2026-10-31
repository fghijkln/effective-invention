import sys, json; sys.path[:0]=['.','tests']
import test_mempress as tm
from omega import progs, fabric, rtl
from omega.ports import mk, ERA, NONE
fabric.ADM=int(sys.argv[1]); K=int(sys.argv[2]); s=int(sys.argv[3])
b=progs.book("treesum",9)
i=tm.ballast_img(b,3,3,1024,8,8,tuple((x,y) for x in range(3) for y in range(3) if (x,y)!=(2,2)))
c=(2,2); fn=[t for t in range(1024) if i.nodes[c][t] is None]; fv=[t for t in range(1024) if i.vars[c][t] is None]
for t in fn[K:]: i.nodes[c][t]=[mk(ERA),mk(ERA)]; i.nown[c][t]=14
for t in fv[K:]: i.vars[c][t]=mk(NONE); i.vown[c][t]=14
r=rtl.run(b,3,3,img=i,seed=s,jitter=30,maxcycles=50_000,timeout=900)
print(r["status"], r["interactions"])
for k,v in sorted(r["cells"].items()): print(k, v)
