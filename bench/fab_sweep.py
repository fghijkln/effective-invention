"""Fabric-model sweep of the spawn threshold K: cycles, msgs/interaction per program and mesh.
usage: fab_sweep.py prog:n[,prog:n] WxH[,WxH] K[,K]"""
import sys, os, json, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from omega import progs, fabric
work = [(p.split(":")[0], int(p.split(":")[1])) for p in sys.argv[1].split(",")]
shapes = [tuple(int(t) for t in s.split("x")) for s in sys.argv[2].split(",")]
ks = [int(k) for k in sys.argv[3].split(",")]
hint = int(sys.argv[4]) if len(sys.argv) > 4 else 0
for name, n in work:
    b = progs.book(name, n)
    for W, H in shapes:
        for k in ks:
            t = time.time()
            f = fabric.Fabric(b, W, H, seed=1, p_msg=1.0, spawn_k=k, spawn_hint=hint, slots=1024 if W * H > 1 else 4096).run()
            r = f.report()
            m = r["msgs"]
            print(json.dumps(dict(prog=f"{name}({n})", mesh=f"{W}x{H}", K=k, hint=hint, cycles=r["cycles"], inter=r["interactions"],
                  mpi=round(sum(m.values()) / r["interactions"], 3), util=round(r["util"], 3), **m, wall=round(time.time() - t, 1))), flush=True)
