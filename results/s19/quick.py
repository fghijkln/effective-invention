import sys,time; sys.path[:0]=['.','tests']
import test_mempress as tm
from omega import progs, fabric
name,N,W,H=("treesum",9,3,3)
book=progs.book(name,N); cells=tuple((x,y) for x in range(W) for y in range(H) if (x,y)!=(W-1,H-1))
bad=[];cyc=[]
for seed in range(int(sys.argv[1]),int(sys.argv[2])+1):
    try:
        f=fabric.Fabric(book,W,H,seed=seed,p_jitter=0.1,img=tm.ballast_img(book,W,H,1024,8,8,cells)).run(); cyc.append(f.cycles)
    except Exception: bad.append(seed)
print("rto",fabric.RTO,"rgrad",fabric.RGRAD,"age",getattr(fabric,"AGE",None),getattr(fabric,"AGEW",None),"bad",bad,"cyc",cyc)
