import sys; sys.path[:0]=['.','tests']
import test_mempress as tm
from omega import progs, fabric
from omega.ports import *
fabric.RTO=int(sys.argv[1]); seed=int(sys.argv[2])
name,N,W,H=("treesum",9,3,3)
book=progs.book(name,N); cells=tuple((x,y) for x in range(W) for y in range(H) if (x,y)!=(W-1,H-1))
f=fabric.Fabric(book,W,H,seed=seed,p_jitter=0.1,img=tm.ballast_img(book,W,H,1024,8,8,cells))
C=f.cells[(2,2)]
names={i:n for n,i in getattr(book,'ids',{}).items()} if hasattr(book,'ids') else {}
for k in range(60):
    for _ in range(500): f.step()
    if all(c.idle() for c in f.cells.values()): print("done",f.cycles); break
    insp=sum(1 for c in f.cells.values() for q in list(c.inq.values())+[c.eject] for m in q if m[0]==2)
    park=sum(1 for c in f.cells.values() if c.rs is not None)
    nunb=sum(1 for v in C.vars if v is not None and tag(v)==NONE) if hasattr(fabric,'NONE') or True else 0
    print(f.cycles,"int",f.interactions,"corner nodes",1024-len(C.nfree),"vars",1024-len(C.vfree),"unbound",nunb,"q",len(C.queue),"spawn-msgs",insp,"parked",park,flush=True)
