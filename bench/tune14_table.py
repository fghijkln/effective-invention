import sys, json
from collections import defaultdict
g = defaultdict(list)
for f in sys.argv[1:]:
    for l in open(f):
        d = json.loads(l); g[(d["prog"], d["mesh"], tuple(d["cfg"]))].append(d)
for k in sorted(g):
    ds = g[k]; n = len(ds)
    print(k, n, "ok" if all(d["ok"] for d in ds) else "FAIL", round(sum(d["cycles"] for d in ds) / n), round(sum(d["mpi"] for d in ds) / n, 3))
