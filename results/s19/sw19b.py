# step 19: more seeds for the big global-pressure meshes (fabric model).  usage: sw19b.py TAG s0 s1
import sys, statistics as S, json; sys.path[:0]=['.','tests']
import test_mempress as tm
from omega import progs, fabric
out={"tag":sys.argv[1],"rto":fabric.RTO,"rgrad":fabric.RGRAD,"cases":{}}
for name,N,W,H in [("treesum",7,8,8),("fib",12,6,6),("qsort",15,6,6),("list",20,3,2)]:
    book=progs.book(name,N); cells=tuple((x,y) for x in range(W) for y in range(H) if (x,y)!=(W-1,H-1))
    bad=[]; cyc=[]
    for seed in range(int(sys.argv[2]),int(sys.argv[3])+1):
        try:
            f=fabric.Fabric(book,W,H,seed=seed,p_jitter=0.1,img=tm.ballast_img(book,W,H,1024,8,8,cells)).run(); cyc.append(f.cycles)
        except Exception as e: bad.append(seed)
    out["cases"][f"{name}({N}) {W}x{H}"]={"livelock":bad,"cycles":round(S.mean(cyc)) if cyc else None,"n":len(cyc)+len(bad)}
    print(json.dumps(out),flush=True)
