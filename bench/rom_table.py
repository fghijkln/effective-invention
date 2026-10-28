"""Step 7 table: RTL cycles per cluster-ROM configuration (results/bench_c*.json) vs the replicated ROM."""
import json, os
CFG = [("c1x1p1", "replicated (1x1)"), ("c2x2p1", "2x2, 1 port"), ("c2x2p2", "2x2, 2 ports"), ("c4x4p1", "4x4, 1 port"), ("c4x4p2", "4x4, 2 ports")]
data = {t: {(r["prog"], r["mesh"].rstrip("*")): r for r in json.load(open(f"results/bench_{t}.json"))}
        for t, _ in CFG if os.path.exists(f"results/bench_{t}.json")}
keys = list(data["c1x1p1"])
print("| program | mesh | " + " | ".join(n for t, n in CFG if t in data) + " |")
print("|---|---|" + "---:|" * len([t for t, _ in CFG if t in data]))
for k in keys:
    base = data["c1x1p1"][k]["cycles"]
    cells = []
    for t, _ in CFG:
        if t not in data: continue
        r = data[t].get(k)
        if r is None: cells.append("—"); continue
        assert r["ok"], (t, k)
        c = r["cycles"]
        cells.append(f"{c:,}" if t == "c1x1p1" else f"{c:,} ({100 * (c / base - 1):+.1f}%)")
    print(f"| {k[0]} | {k[1]} | " + " | ".join(cells) + " |")
