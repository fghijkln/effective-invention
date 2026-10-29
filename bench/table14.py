"""Step 14 table (RTL): step 13 (+s14=0) vs step 14 default, mean / sd / range over seeds, msgs/interaction.
usage: table14.py DEFAULT_CFG jsonl...   (DEFAULT_CFG = s14,govnb,govl0, e.g. 1,3,2)"""
import sys, json, statistics as S
from collections import defaultdict
dflt = tuple(int(v) for v in sys.argv[1].split(","))
g = defaultdict(dict)
for f in sys.argv[2:]:
    for l in open(f):
        d = json.loads(l); g[(d["prog"], d["mesh"], tuple(d["cfg"]))][d["seed"]] = d
PROGS = ["qsort(40)", "list(120)", "sum(1000)", "sort(20)", "higher(100)", "fib(20)", "treesum(9)", "treesum_direct(14)"]
def st(ds):
    c = [d["cycles"] for d in ds]
    return S.mean(c), (S.stdev(c) if len(c) > 1 else 0), max(c) - min(c), S.mean(d["mpi"] for d in ds), len(c), all(d["ok"] for d in ds)
print("| program | mesh | seeds | step 13 cycles mean (sd / range) | **step 14 cycles mean (sd / range)** | Δ mean | Δ sd | step 13 msgs/int | **step 14 msgs/int** |")
print("|---|---|---:|---:|---:|---:|---:|---:|---:|")
for m in ["4x4", "8x8"]:
    for p in PROGS:
        a, b = g.get((p, m, (0, 0, 2))), g.get((p, m, dflt))
        if not a or not b: continue
        seeds = sorted(set(a) & set(b))
        A, B = st([a[s] for s in seeds]), st([b[s] for s in seeds])
        dsd = f"{100 * (B[1] / A[1] - 1):+.0f}%" if A[1] else "–"
        ok = "" if A[5] and B[5] else " **FAIL**"
        print(f"| {p} | {m} | {B[4]} | {A[0]:,.0f} ({A[1]:,.0f} / {A[2]:,}) | **{B[0]:,.0f}** ({B[1]:,.0f} / {B[2]:,}) | {100 * (B[0] / A[0] - 1):+.1f}% | {dsd} | {A[3]:.3f} | **{B[3]:.3f}**{ok} |")
