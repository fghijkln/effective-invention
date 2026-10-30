"""Step 19 RTL table: global-pressure cases, seeds 1-13, three configurations."""
import json, collections, statistics as S
d = collections.defaultdict(dict)
for l in open("results/s18/rto_global.jsonl"):
    r = json.loads(l)
    if r["rto"] in (8, 32): d[(r["case"], f"{r['rto']}/0")][r["seed"]] = r
import os
for l in open("results/s19/rtl_big.jsonl").readlines() + (open("results/s19/rtl_big2.jsonl").readlines() if os.path.exists("results/s19/rtl_big2.jsonl") else []):
    if l.startswith("{"):
        r = json.loads(l)
        if r["rgrad"] == 0: d[(r["case"], f"{r['rto']}/0")][r["seed"]] = r
# rgrad = 0 rows of rtl_ts7.jsonl (seeds 14-30); the step-19 rows come from rtl_fwd.jsonl only (final RTL:
# reserve + full-cell pass-on; rtl_rsv.jsonl / the rgrad=3 rows of rtl_ts7.jsonl are the RTL before the pass-on)
for l in open("results/s19/rtl_ts7.jsonl"):
    if l.startswith("{"):
        r = json.loads(l)
        if r["rgrad"] == 0: d[(r["case"], f"{r['rto']}/0")][r["seed"]] = r
for l in open("results/s19/rtl_fwd.jsonl"):
    if l.startswith("{"):
        r = json.loads(l); d[(r["case"], "8/3")][r["seed"]] = r
cases = list(dict.fromkeys(k[0] for k in d))
cfgs = ["32/0", "8/0", "8/3"]
print("| case | `+rto=32 +rgrad=0` (step 18) | `+rto=8 +rgrad=0` | `+rto=8 +rgrad=3` (step 19) | Δ new vs 32 | Δ new vs 8/0 |")
print("|---|---:|---:|---:|---:|---:|")
cases = [c for c in ["fib(12) 3x3", "treesum(6) 3x3", "list(20) 3x2", "qsort(15) 4x4", "sort(10) 3x3", "fib(12) 6x6", "qsort(15) 6x6", "treesum(7) 8x8"] if c in cases]
for c in cases:
    m = {}; cells = []
    for g in cfgs:
        v = d.get((c, g), {})
        ok = [r for r in v.values() if r["ok"]]; bad = sorted(s for s, r in v.items() if not r["ok"])
        m[g] = S.mean(r["cycles"] for r in ok) if ok else None
        if not ok: cells.append("–"); continue
        cells.append(f"{m[g]:,.0f}" + (f" (**{len(bad)}/{len(v)} stuck**: seed {', '.join(map(str, bad))})" if bad else "") + f" · {S.mean(r['msgs'] for r in ok):,.0f} msgs [{len(v)}]")
    dn = lambda a, b: f"{100 * (m[a] - m[b]) / m[b]:+.1f}%" if m[a] and m[b] else "–"
    print(f"| {c} | " + " | ".join(cells) + f" | {dn('8/3', '32/0')} | {dn('8/3', '8/0')} |")
