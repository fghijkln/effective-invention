"""Step 21 identity check: default (+rto=8 +rgrad=3 +rsv=1) vs results/s15/final_*.jsonl (+ ts_8x8) on programs without pressure."""
import json
ref = {}
for f in ["results/s15/final_4x4.jsonl", "results/s15/final_8x8.jsonl", "results/s15/ts_8x8.jsonl"]:
    for l in open(f):
        d = json.loads(l); ref[(d["prog"], d["mesh"], d["seed"])] = d
n = same = 0; bad = []
for f in ["results/s21/id_4x4.jsonl", "results/s21/id_8x8.jsonl"]:
    for l in open(f):
        d = json.loads(l); k = (d["prog"], d["mesh"], d["seed"]); r = ref.get(k)
        if r is None: bad.append((k, "no reference")); continue
        n += 1
        m0, m1 = sum(r["msgs"].values()), sum(d["msgs"].values())
        if d["ok"] and d["cycles"] == r["cycles"] and d["inter"] == r["inter"] and d["msgs"] == r["msgs"]: same += 1
        else: bad.append((k, f"ok={d['ok']} cycles {r['cycles']}->{d['cycles']} msgs {m0}->{m1} inter {r['inter']}->{d['inter']}"))
print(f"identity: {same}/{n} runs identical to step 15 (cycles, interactions, per-type message counts)")
for b in bad: print("  DIFF", *b)
