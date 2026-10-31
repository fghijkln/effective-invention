import sys, json, time; sys.path[:0]=['.','tests']
import test_mempress as tm
from omega import progs, fabric
name,N,W,H,kn,kv=sys.argv[1],int(sys.argv[2]),int(sys.argv[3]),int(sys.argv[4]),int(sys.argv[5]),int(sys.argv[6])
seeds=[int(x) for x in sys.argv[7].split(',')]
book=progs.book(name,N); want=progs.expected(name,N)
cells=tuple((x,y) for x in range(W) for y in range(H) if (x,y)!=(W-1,H-1))
for s in seeds:
  rec={"p":name,"N":N,"W":W,"H":H,"kn":kn,"kv":kv,"s":s,"rsv":fabric.RSV}
  for po in (1,0):
    fabric.PASSON=po; t=time.time()
    try:
      f=fabric.Fabric(book,W,H,seed=s,p_jitter=0.1,img=tm.ballast_img(book,W,H,1024,kn,kv,cells)).run(max_cycles=400000)
      rec[f"r{po}"]="ok" if f.readback()==want else "WRONG"; rec[f"c{po}"]=f.cycles
      rec[f"ff{po}"]=sum(c.st.get("fwdfull",0) for c in f.cells.values())
    except Exception as e: rec[f"r{po}"]="stuck:"+str(e)[:30]
    rec[f"t{po}"]=round(time.time()-t,1)
  print(json.dumps(rec),flush=True)
