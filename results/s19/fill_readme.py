"""Assemble the README step-19 section from readme_section.md + the data files."""
import json, subprocess, collections
def rows(f):
    return [json.loads(l) for l in open(f) if l.startswith("{")]
def stuck(rs): return sum(1 for r in rs if not r["ok"]), len(rs)
ts9 = collections.defaultdict(list)
for r in rows("results/s19/rtl_ts9.jsonl"): ts9[(r["rto"], r["x"])].append(r)
fwd9 = rows("results/s19/rtl_ts9_fwd.jsonl")
ts7 = collections.defaultdict(dict)
for f in ["results/s19/rtl_big.jsonl", "results/s19/rtl_ts7.jsonl"]:
    for r in rows(f):
        if r["case"] == "treesum(7) 8x8" and r["rgrad"] == 0: ts7[r["rto"]][r["seed"]] = r
for r in rows("results/s18/rto_global.jsonl"):
    if r["case"] == "treesum(7) 8x8" and r["rto"] in (8, 32): ts7[r["rto"]].setdefault(r["seed"], r)
pre7 = {r["seed"]: r for r in rows("results/s19/rtl_rsv.jsonl") + rows("results/s19/rtl_ts7.jsonl") if r["case"] == "treesum(7) 8x8" and r["rgrad"] == 3}
fwd7 = [r for r in rows("results/s19/rtl_fwd.jsonl") if r["case"] == "treesum(7) 8x8"]
oth = collections.defaultdict(list)
for r in rows("results/s19/rtl_fwd.jsonl"):
    if r["case"] != "treesum(7) 8x8": oth["new"].append(r)
f = lambda t: f"{t[0]}/{t[1]}"
live = f"""| case (seeds) | model | `+rto=32 +rgrad=0` (step 18) | `+rto=8 +rgrad=0` | `+rto=8 +rgrad=3` (step 19) |
|---|---|---:|---:|---:|
| treesum(9) 3×3 (1–20) | fabric | 2/20 | **19/20** | **0/20** |
| list(20) 3×2 (1–20) | fabric | 0/20 | 0/20 | 0/20 |
| treesum(7) 8×8, fib(12) 6×6, qsort(15) 6×6, list(20) 3×2 (21–40 each) | fabric | 1/80 | 2/80 | 0/80 |
| treesum(9) 3×3 (1–30) | RTL | {f(stuck(ts9[(32, 'rgrad=0')]))} | **{f(stuck(ts9[(8, 'rgrad=0')]))}** | **{f(stuck(fwd9))}** |
| treesum(7) 8×8 (1–30) | RTL | {f(stuck(list(ts7[32].values())))} | {f(stuck(list(ts7[8].values())))} | {f(stuck(fwd7))} (rules 1–3 only: {f(stuck(list(pre7.values())))}) |
| the other 7 global cases of the cycle table (1–13) | RTL | 0 | 0 | {f(stuck(oth['new']))} |

Fabric: `results/s19/sweep5.jsonl`, `sweep6.jsonl`, `sweep7.jsonl` (final model), `fabric_table.md`; RTL:
`rtl_ts9.jsonl`, `rtl_ts9_fwd.jsonl`, `rtl_big.jsonl`, `rtl_ts7.jsonl`, `rtl_fwd.jsonl` (final RTL)."""
t19 = subprocess.run(["python3", "results/s19/table19.py"], capture_output=True, text=True).stdout.strip()
idc = open("results/s19/idcmp.txt").read().split()[1] + " runs"
s = open("results/s19/readme_section.md").read()
s = s.replace("{LIVETABLE}", live).replace("{T19}", t19).replace("{IDCHK}", idc)
s = s.replace("{T19NOTES}", open("results/s19/t19notes.md").read().strip())
open("results/s19/readme_section_filled.md", "w").write(s)
print(s)
