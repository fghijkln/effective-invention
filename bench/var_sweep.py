"""Seed-variance sweep on the fabric model (resumable).
usage: var_sweep.py prog:n[,..] WxH[,..] seeds out.jsonl [tag] [json-kwargs] [p_msg]
Each (tag, prog, mesh, seed) is appended to out.jsonl; result checked against the semantic model."""
import sys, os, json, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from omega import progs, semantic, fabric
work = [(p.split(":")[0], int(p.split(":")[1])) for p in sys.argv[1].split(",")]
shapes = [tuple(int(t) for t in s.split("x")) for s in sys.argv[2].split(",")]
seeds = [int(s) for s in sys.argv[3].split(",")] if "," in sys.argv[3] else list(range(1, int(sys.argv[3]) + 1))
out = sys.argv[4]
tagn = sys.argv[5] if len(sys.argv) > 5 else "base"
kw = json.loads(sys.argv[6]) if len(sys.argv) > 6 else {}
pm = float(sys.argv[7]) if len(sys.argv) > 7 else 0.5
done = set()
if os.path.exists(out):
    for l in open(out):
        d = json.loads(l); done.add((d["tag"], d["prog"], d["mesh"], d["seed"]))
for W, H in shapes:
    for name, n in work:
        b = progs.book(name, n); ref = None
        for s in seeds:
            key = (tagn, f"{name}({n})", f"{W}x{H}", s)
            if key in done: continue
            if ref is None: ref = semantic.result(b, order="lifo")
            t = time.time()
            slots = 1024 if W * H > 1 else 4096
            f = fabric.Fabric(b, W, H, seed=s, p_msg=pm, slots=slots, qdepth=4096, **kw).run()
            r = f.report(); m = r["msgs"]
            ok = f.readback() == ref["readback"] and f.interactions == ref["interactions"]
            d = dict(tag=tagn, prog=key[1], mesh=key[2], seed=s, ok=ok, cycles=r["cycles"], inter=r["interactions"],
                     mpi=round(sum(m.values()) / r["interactions"], 4), util=round(r["util"], 4), msgs=m, wall=round(time.time() - t, 1))
            with open(out, "a") as fo: fo.write(json.dumps(d) + "\n")
            print(json.dumps(d), flush=True)
