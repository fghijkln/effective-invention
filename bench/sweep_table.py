"""Markdown tables from the step-11/12 sweep logs (results/spawn_sweep*.log, results/seed_sweep*.log)."""
import json, glob
out = ["# Spawn-policy sweeps (RTL, Verilator, cycle accurate)", "",
       "K = spawn_k (threshold for linear-recursion definitions, or for every REF when the hint is off; -1 = none),",
       "hint = fork/rec directory hints, ll = local-first link orientation, K2 = spawn_k2 (threshold for",
       "non-recursive definitions; -1 = none; in the single-seed sweep K2 was not yet separate: non-fork REFs used K).",
       "Base (step 10) = K -1, hint 0, ll 0.", "",
       "## Single seed (seed 1), 4x4 and 8x8", "",
       "| program | mesh | K | hint | ll | cycles | msgs/interaction | util | LINK | NODE | SPAWN |", "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
rows = []
for fn in ["results/spawn_sweep_4x4_noll.jsonl", "results/spawn_sweep.log"]:
    for l in open(fn):
        try: d = json.loads(l)
        except Exception: continue
        d.setdefault("ll", 0); rows.append(d)
seen = set()
for d in sorted(rows, key=lambda d: (d["prog"], d["mesh"], d["hint"], d["ll"], d["K"])):
    k = (d["prog"], d["mesh"], d["K"], d["hint"], d["ll"])
    if k in seen: continue
    seen.add(k)
    out.append(f"| {d['prog']} | {d['mesh']} | {d['K']} | {d['hint']} | {d['ll']} | {d['cycles']:,} | {d['mpi']:.3f} | {100*d['util']:.0f}% | {d['link']:,} | {d['node']:,} | {d['spawn']:,} |")
out += ["", "## Mean of seeds 1-4 (arbitration / priority seed), 8x8", "",
        "| program | K | hint | ll | K2 | cycles per seed | mean | msgs/interaction |", "|---|---:|---:|---:|---:|---|---:|---:|"]
for fn in sorted(glob.glob("results/seed_sweep*.log")):
    for l in open(fn):
        try: d = json.loads(l)
        except Exception: continue
        out.append(f"| {d['prog']} | {d['K']} | {d['hint']} | {d['ll']} | {d.get('K2', d['K'] if d['hint'] else '-')} | {', '.join(f'{c:,}' for c in d['cycles'])} | {d['mean']:,} | {d['mpi']:.3f} |")
open("results/spawn_sweep.md", "w").write("\n".join(out) + "\n")
print(len(out))
