# step 20: fabric perf on the 3 cases that lost under step 19 (+ treesum(9) 3x3 livelock count optional)
# usage: [env knobs] perf.py TAG seeds [cases]   cases: comma list of t6,l20,f6,t9,t7,q6,f3,q4,s10
import sys, os, statistics as S, json, time; sys.path[:0]=['.','tests']
import test_mempress as tm
from omega import progs, fabric
C={"t6":("treesum",6,3,3),"l20":("list",20,3,2),"f6":("fib",12,6,6),"t9":("treesum",9,3,3),"t7":("treesum",7,8,8),
   "q6":("qsort",15,6,6),"f3":("fib",12,3,3),"q4":("qsort",15,4,4),"s10":("sort",10,3,3)}
tag=sys.argv[1]; s0,s1=[int(v) for v in sys.argv[2].split("-")]; cs=(sys.argv[3] if len(sys.argv)>3 else "t6,l20,f6").split(",")
knobs={k:v for k,v in os.environ.items() if k.startswith("OMEGA_")}
for c in cs:
    name,N,W,H=C[c]; book=progs.book(name,N); cells=tuple((x,y) for x in range(W) for y in range(H) if (x,y)!=(W-1,H-1))
    bad=[]; cyc=[]; msgs=[]; t=time.time()
    for seed in range(s0,s1+1):
        try:
            f=fabric.Fabric(book,W,H,seed=seed,p_jitter=0.1,img=tm.ballast_img(book,W,H,1024,8,8,cells)).run(); cyc.append(f.cycles)
            msgs.append(sum(f.msgs.values()) if isinstance(getattr(f,'msgs',None),dict) else getattr(f,'msgs',0))
        except Exception as e: bad.append(seed)
    print(json.dumps({"tag":tag,"knobs":knobs,"case":f"{name}({N}) {W}x{H}","seeds":sys.argv[2],"livelock":bad,"cycles":round(S.mean(cyc)) if cyc else None,"cyc":cyc,"sec":round(time.time()-t)}),flush=True)
