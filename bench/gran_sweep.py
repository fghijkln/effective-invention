"""Step 13 fabric-model sweep of the adaptive granularity policy.
usage: gran_sweep.py prog:n[,..] WxH[,..] cfg[;cfg..] seeds   cfg = G,Klo,Khi,init  (G=0: step 12)"""
import sys, os, json, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from omega import progs, fabric
work = [(p.split(":")[0], int(p.split(":")[1])) for p in sys.argv[1].split(",")]
shapes = [tuple(int(t) for t in s.split("x")) for s in sys.argv[2].split(",")]
cfgs = [tuple(int(v) for v in c.split(",")) for c in sys.argv[3].split(";")]
seeds = range(1, int(sys.argv[4]) + 1)
for name, n in work:
    b = progs.book(name, n)
    for W, H in shapes:
        for g in cfgs:
            cs, mp, ut = [], [], []
            for s in seeds:
                f = fabric.Fabric(b, W, H, seed=s, p_msg=1.0, gran=g, slots=1024 if W * H > 1 else 4096, qdepth=4096).run()
                r = f.report()
                cs.append(r["cycles"]); mp.append(sum(r["msgs"].values()) / r["interactions"]); ut.append(r["util"])
            print(json.dumps(dict(prog=f"{name}({n})", mesh=f"{W}x{H}", gran=g, cycles=cs, mean=round(sum(cs) / len(cs)),
                  mpi=round(sum(mp) / len(mp), 3), util=round(sum(ut) / len(ut), 3))), flush=True)
