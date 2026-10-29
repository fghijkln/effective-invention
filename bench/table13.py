"""Step 12 vs step 13 table from the sweep13 jsonl files (means over seeds)."""
import json, glob
from collections import defaultdict
g = defaultdict(list)
for f in ["results/s13_8x8.jsonl", "results/s13_small.jsonl", "results/s13_8x8_par.jsonl"]:
    for l in open(f):
        d = json.loads(l); g[(d["prog"], d["mesh"], tuple(d["cfg"]))].append(d)
S12, S13, KP4 = (16, 4, 16, 0), (16, 4, 4, 30), (16, 4, 4, 0)
def st(p, m, c):
    ds = g.get((p, m, c)) or (g.get((p, m, S12)) if m == "1x1" else None)
    if not ds: return None
    n = len(ds)
    return sum(d["cycles"] for d in ds) / n, sum(d["mpi"] for d in ds) / n, sum(d["util"] for d in ds) / n, n
progs = ["qsort(40)", "list(120)", "sum(1000)", "sort(20)", "higher(100)", "fact(20)", "fib(20)", "treesum(9)", "treesum_direct(14)"]
print("| program | mesh | seeds | step 12 cycles | step 13 cycles | change | step 12 msgs/int | step 13 msgs/int | step 12 util | step 13 util | vs 1×1 (step 13) | static kp=4, no governor: cycles / msgs/int |")
print("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|")
for p in progs:
    one = st(p, "1x1", S12)
    for m in ["2x2", "4x4", "8x8"]:
        a, b, k = st(p, m, S12), st(p, m, S13), st(p, m, KP4)
        if not a or not b: continue
        vs = f"{one[0] / b[0]:.2f}×" if one else "–"
        kk = f"{k[0]:,.0f} / {k[1]:.3f}" if k else "–"
        print(f"| {p} | {m} | {b[3]} | {a[0]:,.0f} | **{b[0]:,.0f}** | {100 * (b[0] / a[0] - 1):+.1f}% | {a[1]:.3f} | **{b[1]:.3f}** | {100 * a[2]:.1f}% | {100 * b[2]:.1f}% | {vs} | {kk} |")
