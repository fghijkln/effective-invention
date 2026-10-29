"""Step 13 RTL sweep (resumable): prog:n[,..] WxH[,..] cfg[;cfg..] seeds out.jsonl
cfg = K,K2,KP,GOV (hint 1, link-local 1).  Each finished (prog, mesh, cfg, seed) is appended to out.jsonl
and skipped on a re-run."""
import sys, os, json, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from omega import progs, semantic, rtl
work = [(p.split(":")[0], int(p.split(":")[1])) for p in sys.argv[1].split(",")]
shapes = [tuple(int(t) for t in s.split("x")) for s in sys.argv[2].split(",")]
cfgs = [tuple(int(v) for v in c.split(",")) for c in sys.argv[3].split(";")]
seeds = [int(s) for s in sys.argv[4].split(",")] if "," in sys.argv[4] else list(range(1, int(sys.argv[4]) + 1))
out = sys.argv[5]
done = set()
if os.path.exists(out):
    for l in open(out):
        try:
            d = json.loads(l); done.add((d["prog"], d["mesh"], tuple(d["cfg"]), d["seed"]))
        except Exception:
            pass
for W, H in shapes:
    for name, n in work:
        b = progs.book(name, n); ref = None
        for c in cfgs:
            for s in seeds:
                key = (f"{name}({n})", f"{W}x{H}", c, s)
                if key in done or (W * H == 1 and (c != cfgs[0] or s != seeds[0])):
                    continue
                if ref is None:
                    ref = semantic.result(b, order="lifo")
                t = time.time()
                k, k2, kp, gov = c
                r = rtl.run(b, W, H, seed=s, spawn=(k, 1, k2, kp, gov), link_local=1, maxcycles=200_000_000, timeout=7200)
                if r["status"] != 0:      # as bench.py: a program that does not fit 1024-slot cells gets 4096
                    r = rtl.run(b, W, H, seed=s, spawn=(k, 1, k2, kp, gov), link_local=1, maxcycles=200_000_000, timeout=7200, slots=4096)
                ok = r["readback"] == ref["readback"] and r["interactions"] == ref["interactions"]
                m = r["msgs"]
                d = dict(prog=key[0], mesh=key[1], cfg=list(c), seed=s, ok=ok, cycles=r["cycles"], inter=r["interactions"],
                         mpi=round(sum(m.values()) / r["interactions"], 4), util=round(r.get("util", 0), 4), msgs=m, wall=round(time.time() - t, 1))
                with open(out, "a") as f:
                    f.write(json.dumps(d) + "\n")
                print(json.dumps(d), flush=True)
