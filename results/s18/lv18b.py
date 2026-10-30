import sys, statistics as S; sys.path[:0]=['.','tests']
import test_mempress as tm
from omega import progs, fabric
fabric.RTO=int(sys.argv[1]); fabric.ESCN=int(sys.argv[2])
G=[("treesum",9,3,3),("list",20,3,2)]+tm.GLOBAL+[("fib", 12, 6, 6), ("treesum", 7, 8, 8)]
for name,N,W,H in G:
    book=progs.book(name,N); cells=tuple((x,y) for x in range(W) for y in range(H) if (x,y)!=(W-1,H-1))
    bad=[]; cyc=[]
    for seed in range(1,21 if (name,N) in (("treesum",9),("list",20)) else 4):
        try:
            f=fabric.Fabric(book,W,H,seed=seed,p_jitter=0.1,img=tm.ballast_img(book,W,H,1024,8,8,cells)).run(); cyc.append(f.cycles)
        except Exception as e: bad.append(seed)
    print(sys.argv[1],sys.argv[2],name,N,W,H,"livelock",bad,"cycles",round(S.mean(cyc)) if cyc else None,flush=True)
