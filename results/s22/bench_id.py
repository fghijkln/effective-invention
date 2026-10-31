# step 22: standard benchmarks on the fabric model, default vs ADM knob (env OMEGA_ADM read at import: run twice)
import sys, os, json, time; sys.path[:0]=['.','tests']
from omega import progs, fabric
P=[("fib",20),("treesum",9),("treesum_direct",14),("qsort",40),("list",120),("sum",1000),("sort",20),("higher",100),("fact",10)]
for mesh in sys.argv[1].split(","):
  W,H=map(int,mesh.split("x"))
  for name,N in P:
    for s in (1,2):
      b=progs.book(name,N); t=time.time()
      f=fabric.Fabric(b,W,H,seed=s,p_jitter=0.1).run()
      mf=min(min(c.st.get("min_free", 1024) for c in f.cells.values()),1024)
      print(json.dumps({"adm":fabric.ADM,"prog":f"{name}({N})","mesh":mesh,"seed":s,"ok":f.readback()==progs.expected(name,N),
        "cycles":f.cycles,"inter":f.interactions,"maxn":max(c.st["max_nodes"] for c in f.cells.values()),
        "maxv":max(c.st.get("max_vars",0) for c in f.cells.values()),"sec":round(time.time()-t)}),flush=True)
