# step 19 sweep: livelock seeds + mean cycles on the global-pressure set, fabric model.
# usage: sw19.py TAG  (config via OMEGA_RTO / OMEGA_RBO / OMEGA_RJIT / OMEGA_RRST)
import sys, os, statistics as S, json; sys.path[:0]=['.','tests']
import test_mempress as tm
from omega import progs, fabric
NS=int(os.environ.get("NS","20"))
G=[("treesum",9,3,3),("list",20,3,2)]+tm.GLOBAL+[("fib",12,6,6),("treesum",7,8,8)]
out={"tag":sys.argv[1],"rto":fabric.RTO,"rgrad":fabric.RGRAD,"rbo":getattr(fabric,"RBO",0),"rjit":getattr(fabric,"RJIT",0),"rrst":getattr(fabric,"RRST",0),"cases":{}}
for name,N,W,H in G:
    k=f"{name}({N}) {W}x{H}"
    if k in out["cases"]: continue
    book=progs.book(name,N); cells=tuple((x,y) for x in range(W) for y in range(H) if (x,y)!=(W-1,H-1))
    bad=[]; cyc=[]
    for seed in range(1,NS+1 if (name,N) in (("treesum",9),("list",20)) else 4):
        try:
            f=fabric.Fabric(book,W,H,seed=seed,p_jitter=0.1,img=tm.ballast_img(book,W,H,1024,8,8,cells)).run(); cyc.append(f.cycles)
        except Exception as e: bad.append(seed)
    out["cases"][k]={"livelock":bad,"cycles":round(S.mean(cyc)) if cyc else None,"n":len(cyc)+len(bad)}
print(json.dumps(out),flush=True)
