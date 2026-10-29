"""RTL sweep of the step-11 spawn policy: threshold K (-1 = always) with / without the fork hint.
usage: spawn_sweep.py prog:n[,..] WxH[,..] K[,..] hint[,..] [link_local[,..]] [--out results/spawn_sweep.jsonl]"""
import sys, os, json, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from omega import progs, semantic, rtl
work = [(p.split(":")[0], int(p.split(":")[1])) for p in sys.argv[1].split(",")]
shapes = [tuple(int(t) for t in s.split("x")) for s in sys.argv[2].split(",")]
ks = [int(k) for k in sys.argv[3].split(",")]
hs = [int(h) for h in sys.argv[4].split(",")]
lls = [int(v) for v in sys.argv[5].split(",")] if len(sys.argv) > 5 and not sys.argv[5].startswith("--") else [0]
out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else "results/spawn_sweep.jsonl"
for name, n in work:
    b = progs.book(name, n)
    ref = semantic.result(b, order="lifo")
    for W, H in shapes:
        for h in hs:
            for k in ks:
              for ll in lls:
                t = time.time()
                r = rtl.run(b, W, H, maxcycles=200_000_000, timeout=3600, spawn=(k, h), link_local=ll)
                m = r["msgs"]
                row = dict(prog=f"{name}({n})", mesh=f"{W}x{H}", K=k, hint=h, ll=ll, ok=r["readback"] == ref["readback"] and r["interactions"] == ref["interactions"],
                           cycles=r["cycles"], mpi=round(sum(m.values()) / r["interactions"], 3), util=round(r["util"], 3),
                           link=m["msg_link"], node=m["msg_node"], spawn=m["msg_spawn"], wall=round(time.time() - t, 1))
                print(json.dumps(row), flush=True)
                with open(out, "a") as f:
                    f.write(json.dumps(row) + "\n")
