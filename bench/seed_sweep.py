"""Multi-seed RTL comparison of spawn policies (the 8x8 schedule varies a lot with the arbitration /
priority seed).  usage: seed_sweep.py prog:n[,..] WxH cfg[;cfg..] seeds   cfg = K,hint,link_local[,K2]"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from omega import progs, semantic, rtl
work = [(p.split(":")[0], int(p.split(":")[1])) for p in sys.argv[1].split(",")]
W, H = (int(t) for t in sys.argv[2].split("x"))
cfgs = [(tuple(int(v) for v in c.split(",")) + (-1,))[:4] for c in sys.argv[3].split(";")]
seeds = range(1, int(sys.argv[4]) + 1)
for name, n in work:
    b = progs.book(name, n); ref = semantic.result(b, order="lifo")
    for k, h, ll, k2 in cfgs:
        cs, mp, ok = [], [], True
        for s in seeds:
            r = rtl.run(b, W, H, seed=s, spawn=(k, h, k2), link_local=ll, maxcycles=200_000_000, timeout=3600)
            ok &= r["readback"] == ref["readback"] and r["interactions"] == ref["interactions"]
            cs.append(r["cycles"]); mp.append(sum(r["msgs"].values()) / r["interactions"])
        print(json.dumps(dict(prog=f"{name}({n})", mesh=f"{W}x{H}", K=k, hint=h, ll=ll, K2=k2, ok=ok, cycles=cs,
                              mean=round(sum(cs) / len(cs)), mpi=round(sum(mp) / len(mp), 3))), flush=True)
