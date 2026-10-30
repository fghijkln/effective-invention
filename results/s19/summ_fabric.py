import json, glob
rows=[]
for f in ["results/s19/sweep1.jsonl","results/s19/sweep3_minrd.jsonl","results/s19/sweep3.jsonl","results/s19/sweep4.jsonl"]:
    for l in open(f):
        if l.startswith("{"): rows.append(json.loads(l))
keys=list(rows[0]["cases"])
print("| config | " + " | ".join(keys) + " |"); print("|---|" + "---:|"*len(keys))
for r in rows:
    print(f"| {r['tag']} | " + " | ".join(f"{len(r['cases'][k]['livelock'])}/{r['cases'][k]['n']} · {r['cases'][k]['cycles']}" for k in keys) + " |")
