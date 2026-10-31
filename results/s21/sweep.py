# step 21: search default-config (+rsv=1) scenarios where the full-cell pass-on (rule d) matters.
# usage: sweep.py OUT  (fabric model; OMEGA_PASSON toggled in-process)
import sys, json, time; sys.path[:0]=['.','tests']
import test_mempress as tm
from omega import progs, fabric
out=open(sys.argv[1],'a')
PROGS=[("treesum",6),("fib",12),("list",20),("sort",10),("qsort",15),("treesum",7)]
SHAPES=[(3,3),(4,4),(3,2),(4,3)]
KEEPS=[4,6,8,12]
for name,N in PROGS:
  book=progs.book(name,N); want=progs.expected(name,N)
  for W,H in SHAPES:
    cells=tuple((x,y) for x in range(W) for y in range(H) if (x,y)!=(W-1,H-1))
    for k in KEEPS:
      for s in range(1,7):
        rec={"p":name,"N":N,"W":W,"H":H,"k":k,"s":s}
        for po in (1,0):
          fabric.PASSON=po; t=time.time()
          try:
            f=fabric.Fabric(book,W,H,seed=s,p_jitter=0.1,img=tm.ballast_img(book,W,H,1024,k,k,cells)).run(max_cycles=400000)
            rec[f"r{po}"]="ok" if f.readback()==want else "WRONG"; rec[f"c{po}"]=f.cycles
            rec[f"ff{po}"]=sum(c.st.get("fwdfull",0) for c in f.cells.values())
          except Exception as e: rec[f"r{po}"]="stuck:"+str(e)[:30]
          rec[f"t{po}"]=round(time.time()-t,1)
        out.write(json.dumps(rec)+"\n"); out.flush()
        if rec["r1"]!="ok" and rec["r0"]!="ok": break   # both stuck: memory too small at this keep
