"""Summarise a sweep13 jsonl: mean cycles / msgs per interaction / util per (prog, mesh, cfg)."""
import sys, json
from collections import defaultdict
g = defaultdict(list)
for f in sys.argv[1:]:
    for l in open(f):
        d = json.loads(l); g[(d["prog"], d["mesh"], tuple(d["cfg"]))].append(d)
print("| program | mesh | K,K2,KP,GOV | ok | cycles per seed | mean | msgs/int | util |")
print("|---|---|---|---|---|---:|---:|---:|")
for (p, m, c), ds in sorted(g.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2])):
    cs = [d["cycles"] for d in sorted(ds, key=lambda d: d["seed"])]
    print(f"| {p} | {m} | {','.join(map(str, c))} | {all(d['ok'] for d in ds)} | {', '.join(f'{x:,}' for x in cs)} | {round(sum(cs)/len(cs)):,} | "
          f"{sum(d['mpi'] for d in ds)/len(ds):.3f} | {100*sum(d['util'] for d in ds)/len(ds):.1f}% |")
