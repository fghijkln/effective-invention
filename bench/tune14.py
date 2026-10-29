"""Step 14 governor tuning sweep (RTL, resumable): prog:n[,..] WxH cfg[;cfg..] seeds out.jsonl ; cfg = s14,govnb,govl0"""
import sys, os, json, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from omega import progs, semantic, rtl
work = [(p.split(":")[0], int(p.split(":")[1])) for p in sys.argv[1].split(",")]
W, H = (int(t) for t in sys.argv[2].split("x"))
cfgs = [tuple(int(v) for v in c.split(",")) for c in sys.argv[3].split(";")]
seeds = list(range(1, int(sys.argv[4]) + 1)); out = sys.argv[5]
done = set()
if os.path.exists(out):
    for l in open(out):
        d = json.loads(l); done.add((d["prog"], tuple(d["cfg"]), d["seed"]))
for name, n in work:
    b = progs.book(name, n); ref = semantic.result(b, order="lifo")
    for c in cfgs:
        for s in seeds:
            if (f"{name}({n})", c, s) in done: continue
            r = rtl.run(b, W, H, seed=s, s14=c[0], govnb=c[1], govl0=c[2], maxcycles=200_000_000, timeout=7200)
            ok = r["readback"] == ref["readback"] and r["interactions"] == ref["interactions"]
            d = dict(prog=f"{name}({n})", mesh=f"{W}x{H}", cfg=list(c), seed=s, ok=ok, cycles=r["cycles"],
                     mpi=round(sum(r["msgs"].values()) / r["interactions"], 4), fgive=r["fgive"])
            open(out, "a").write(json.dumps(d) + "\n"); print(json.dumps(d), flush=True)
