import sys; sys.path[:0]=['.','tests']
import test_mempress as tm
from omega import progs, fabric
rto=int(sys.argv[1]); fabric.RTO=rto
G=tm.GLOBAL+[("treesum",9,3,3)]
for name,N,W,H in G:
    book=progs.book(name,N); cells=tuple((x,y) for x in range(W) for y in range(H) if (x,y)!=(W-1,H-1))
    bad=[]
    for seed in range(1,21):
        try:
            fabric.Fabric(book,W,H,seed=seed,p_jitter=0.1,img=tm.ballast_img(book,W,H,1024,8,8,cells)).run()
        except Exception as e: bad.append(seed)
    print(rto,name,N,W,H,"livelock seeds",bad,flush=True)
