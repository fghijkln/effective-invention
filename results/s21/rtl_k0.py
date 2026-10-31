# step 21: ballast keep 0 free node slots (8 vars) in the program's home cell (0,0): RTL correct design vs mutant 50
import sys, json; sys.path[:0]=['.','tests']
import test_mempress as tm
from omega import progs, fabric, rtl, semantic
kv=int(sys.argv[1]) if len(sys.argv)>1 else 8
for j,(name,N) in enumerate(tm.BALLAST):
  b=progs.book(name,N); want=progs.expected(name,N); ref=semantic.result(b,fuel=10**8)
  for W,H in tm.BSHAPES:
    for seed in (j+3,):
      rec={"p":name,"N":N,"W":W,"H":H,"kv":kv,"seed":seed}
      for m in (0,1<<50):
        r=rtl.run(b,W,H,img=tm.ballast_img(b,W,H,1024,0,kv),seed=seed,jitter=30,mut=m,maxcycles=300_000,timeout=600)
        ok=r["status"]==0 and r["readback"]==want and r["interactions"]==ref["interactions"]
        rec["mut" if m else "ok"]=(r["status"],ok,r["cycles"],sum(c.get("fwdfull",0) for c in r["cells"].values()))
      print(json.dumps(rec),flush=True)
