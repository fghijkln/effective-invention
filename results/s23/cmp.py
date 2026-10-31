"""Step 23: cycles per (prog, mesh) of +ilr=1 / +ilr=2 vs step 22 (= results/s15 references for 4x4/8x8, results/s23/b4_ilr0.jsonl for 1x1/2x2)."""
import json, os, collections, statistics as st
def load(fs):
    d = {}
    for f in fs:
        if os.path.exists(f):
            for l in open(f):
                r = json.loads(l); d[(r["prog"], r["mesh"], r["seed"])] = r
    return d
base = load(["results/s23/id_4x4.jsonl", "results/s23/id_8x8.jsonl", "results/s23/b4_ilr0.jsonl"])
if not any(k[1] == "8x8" for k in base):
    base.update(load(["results/s15/final_8x8.jsonl", "results/s15/ts_8x8.jsonl"]))
cfg = {i: load([f"results/s23/b4_ilr{i}.jsonl", f"results/s23/b8_ilr{i}.jsonl"]) for i in (1, 2)}
# sum(1000) 1x1: the sweep's slots=4096 retry keeps qdepth 1024, which ilr >= 1 overflows; use the qdepth-4096 runs
q = json.load(open("results/s23/sum1x1_q4096.json"))
for k in list(base):
    if k[0] == "sum(1000)" and k[1] == "1x1":
        for i in (1, 2):
            if k in cfg[i]: cfg[i][k] = dict(cfg[i][k], ok=True, cycles=q[str(i)]["cycles"])
progs = []; meshes = ["1x1", "2x2", "4x4", "8x8"]
for k in base:
    if k[0] not in progs: progs.append(k[0])
print("| program | mesh | seeds | step 22 cycles (mean) | +ilr=1 | Δ | +ilr=2 | Δ | all ok |")
print("|---|---|---:|---:|---:|---:|---:|---:|---|")
tot = {1: [], 2: []}
for m in meshes:
    for p in progs:
        ks = [k for k in base if k[0] == p and k[1] == m and all(k in cfg[i] for i in (1, 2))]
        if not ks: continue
        b = st.mean(base[k]["cycles"] for k in ks)
        row = [p, m, str(len(ks)), f"{b:,.0f}"]
        ok = all(base[k]["ok"] and cfg[i][k]["ok"] for k in ks for i in (1, 2))
        for i in (1, 2):
            c = st.mean(cfg[i][k]["cycles"] for k in ks); tot[i].append(c / b)
            row += [f"{c:,.0f}", f"{100 * (c / b - 1):+.1f}%"]
        print("| " + " | ".join(row) + f" | {'yes' if ok else 'NO'} |")
for i in (1, 2):
    if tot[i]: print(f"\n+ilr={i}: geometric-ish mean ratio {st.geometric_mean(tot[i]):.4f} over {len(tot[i])} (prog, mesh) cells")
