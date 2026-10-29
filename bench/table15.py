"""Step 15 table (RTL): step 14 default (results/s14/final_*.jsonl, cfg [2,0,2]) vs step 15 (results/s15/*.jsonl, s14 = 2
with the step-15 directory bit 59), mean / sd / range of cycles and mean msgs/interaction over the common seeds.
usage: table15.py"""
import json, glob, os, statistics as S
from collections import defaultdict
R = os.path.join(os.path.dirname(__file__), "..", "results")
old, new = defaultdict(dict), defaultdict(dict)
for f in glob.glob(os.path.join(R, "s14", "final_*.jsonl")):
    for l in open(f):
        d = json.loads(l)
        if d["cfg"] == [2, 0, 2]:
            old[(d["prog"], d["mesh"])][d["seed"]] = d
for f in sorted(glob.glob(os.path.join(R, "s15", "*.jsonl"))):
    for l in open(f):
        d = json.loads(l)
        if d.get("s14", 2) == 2:
            new[(d["prog"], d["mesh"])][d["seed"]] = d
PROGS = ["qsort(40)", "list(120)", "sum(1000)", "sort(20)", "higher(100)", "fib(20)", "treesum(9)", "treesum_direct(14)"]


def st(ds):
    c = [d["cycles"] for d in ds]
    return S.mean(c), (S.stdev(c) if len(c) > 1 else 0), max(c) - min(c), S.mean(d["mpi"] for d in ds), all(d["ok"] for d in ds)


print("| program | mesh | seeds | step 14 cycles mean (sd / range) | **step 15 cycles mean (sd / range)** | Δ mean | step 14 msgs/int | **step 15 msgs/int** |")
print("|---|---|---:|---:|---:|---:|---:|---:|")
for m in ["4x4", "8x8"]:
    for p in PROGS:
        a, b = old.get((p, m)), new.get((p, m))
        if not a or not b:
            continue
        seeds = sorted(set(a) & set(b))
        A, B = st([a[s] for s in seeds]), st([b[s] for s in seeds])
        ok = "" if A[4] and B[4] else " **FAIL**"
        print(f"| {p} | {m.replace('x', '×')} | {len(seeds)} | {A[0]:,.0f} ({A[1]:,.0f} / {A[2]:,}) | **{B[0]:,.0f}** ({B[1]:,.0f} / {B[2]:,}) | "
              f"{100 * (B[0] / A[0] - 1):+.1f}% | {A[3]:.3f} | **{B[3]:.3f}**{ok} |")
