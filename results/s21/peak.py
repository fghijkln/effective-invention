# step 22: peak live slots (whole fabric) of a run without pressure, sampled every cycle
import sys, os; sys.path[:0]=['.','tests']
from omega import progs, fabric
name,N,W,H=sys.argv[1],int(sys.argv[2]),int(sys.argv[3]),int(sys.argv[4]); seed=int(sys.argv[5]) if len(sys.argv)>5 else 1
b=progs.book(name,N); f=fabric.Fabric(b,W,H,seed=seed,p_jitter=0.1)
S=f.slots*W*H; base_n=sum(len(c.nfree) for c in f.cells.values()); base_v=sum(len(c.vfree) for c in f.cells.values())
pn=pv=0
while True:
    f.step()
    un=base_n-sum(len(c.nfree) for c in f.cells.values()); uv=base_v-sum(len(c.vfree) for c in f.cells.values())
    pn=max(pn,un); pv=max(pv,uv)
    if all(c.idle() for c in f.cells.values()): break
print(f"{name}({N}) {W}x{H} seed {seed} knobs {dict((k,v) for k,v in os.environ.items() if k.startswith('OMEGA_ADM') or k=='OMEGA_LM_T')}: cycles {f.cycles} peak nodes {pn} vars {pv} (beyond the image)")
