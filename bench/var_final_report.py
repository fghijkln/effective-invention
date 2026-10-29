"""Step 14 final comparison tables (fabric model, p_msg 0.5, 1024-slot cells).
usage: var_final_report.py > results/var/final_tables.md"""
import json, statistics as S, os
from collections import defaultdict
R = os.path.join(os.path.dirname(__file__), "..", "results", "var")
TAGS = ["base", "kp4", "s14c", "s14a", "s14b"]
PROGS = ["qsort(40)", "list(120)", "sum(1000)", "sort(20)", "higher(100)", "fib(20)", "treesum(9)", "treesum_direct(14)"]


def load(fn):
    g = defaultdict(list)
    p = os.path.join(R, fn)
    if os.path.exists(p):
        for l in open(p):
            d = json.loads(l)
            g[(d["tag"], d["prog"], d["mesh"])].append(d)
    return g


def st(v):
    c = [x["cycles"] for x in v]
    return dict(n=len(c), ok=all(x["ok"] for x in v), mu=S.mean(c), sd=S.pstdev(c), rg=max(c) - min(c),
                mpi=S.mean(x["mpi"] for x in v))


g = load("full.jsonl")
print("## 1. All programs (8×8 treesum/treesum_direct/fib: seeds 1–8; others seeds 1–4)\n")
print("cell = mean cycles, Δ vs base, (sd / range), [msgs/int]\n")
print("| program | mesh | " + " | ".join(TAGS) + " |")
print("|---|---|" + "---:|" * len(TAGS))
for p in PROGS:
    for m in ["2x2", "4x4", "8x8"]:
        if ("base", p, m) not in g:
            continue
        b = st(g[("base", p, m)])
        row = []
        for t in TAGS:
            if (t, p, m) not in g:
                row.append("–"); continue
            s = st(g[(t, p, m)])
            d = "" if t == "base" else f" {100 * (s['mu'] / b['mu'] - 1):+.1f}%"
            row.append(f"{s['mu']:,.0f}{d} ({s['sd']:,.0f}/{s['rg']:,}) [{s['mpi']:.2f}]" + ("" if s["ok"] else " **FAIL**"))
        print(f"| {p} | {m} | " + " | ".join(row) + " |")

print("\n## 2. 4×4 → 8×8 speed-up (mean 4×4 / mean 8×8)\n")
print("| program | " + " | ".join(TAGS) + " |")
print("|---|" + "---:|" * len(TAGS))
for p in PROGS:
    row = []
    for t in TAGS:
        a, b = g.get((t, p, "4x4")), g.get((t, p, "8x8"))
        row.append(f"{st(a)['mu'] / st(b)['mu']:.2f}×" if a and b else "–")
    print(f"| {p} | " + " | ".join(row) + " |")

t = load("t16.jsonl")
if t:
    print("\n## 3. treesum(9) 8×8, seeds 1–16\n")
    print("| config | mean | Δ mean | sd | Δ sd | min | max | range | Δ range | msgs/int |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    b = st(t[("base", "treesum(9)", "8x8")])
    for tg in ["base", "s14c", "s14a", "s14b"]:
        v = t.get((tg, "treesum(9)", "8x8"))
        if not v:
            continue
        s = st(v); c = [x["cycles"] for x in v]
        print(f"| {tg} | {s['mu']:,.0f} | {100 * (s['mu'] / b['mu'] - 1):+.1f}% | {s['sd']:,.0f} | {100 * (s['sd'] / b['sd'] - 1):+.0f}% | "
              f"{min(c):,} | {max(c):,} | {s['rg']:,} | {100 * (s['rg'] / b['rg'] - 1):+.0f}% | {s['mpi']:.3f} |" + ("" if s["ok"] else " FAIL"))
