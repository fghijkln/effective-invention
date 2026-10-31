# step 21: scenarios with very few free node slots (where the pass-on can fire), fabric model, default knobs.
import sys, json, time, itertools; sys.path[:0]=['.','tests']
import test_mempress as tm
from omega import progs, fabric
out=open(sys.argv[1],'a'); mode=sys.argv[2]
PROGS=[("treesum",6),("fib",12),("list",20),("sort",10),("qsort",15)]
SHAPES=[(2,2),(3,2),(3,3),(4,4)]
KEEPS=[(0,8),(0,30),(1,8),(1,30),(2,8),(2,30),(1,1),(2,2),(3,3)]
for (name,N),(W,H),(kn,kv) in itertools.product(PROGS,SHAPES,KEEPS):
  book=progs.book(name,N); want=progs.expected(name,N)
  cells=((0,0),) if mode=="one" else tuple((x,y) for x in range(W) for y in range(H) if (x,y)!=(W-1,H-1))
  for s in range(1,4):
    rec={"m":mode,"p":name,"N":N,"W":W,"H":H,"kn":kn,"kv":kv,"s":s}
    for po in (1,0):
      fabric.PASSON=po; t=time.time()
      try:
        f=fabric.Fabric(book,W,H,seed=s,p_jitter=0.1,img=tm.ballast_img(book,W,H,1024,kn,kv,cells)).run(max_cycles=300000)
        rec[f"r{po}"]="ok" if f.readback()==want else "WRONG"; rec[f"c{po}"]=f.cycles
        rec[f"ff{po}"]=sum(c.st.get("fwdfull",0) for c in f.cells.values())
      except Exception as e: rec[f"r{po}"]="stuck:"+str(e)[:30]
      rec[f"t{po}"]=round(time.time()-t,1)
      if po==1 and rec["r1"]!="ok": break
    out.write(json.dumps(rec)+"\n"); out.flush()
    if rec["r1"]!="ok": break
