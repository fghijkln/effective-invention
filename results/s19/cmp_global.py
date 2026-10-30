import json,collections,statistics as S,sys
d=collections.defaultdict(list)
for l in open('results/s18/rto_global.jsonl'):
    r=json.loads(l); d[(r['case'],f"rto{r['rto']}")].append(r)
for f,tag in [('results/s19/rto_global_g.jsonl','rto8+g7'),('results/s19/rto_global_g3.jsonl','rto8+g3'),('results/s19/rto_global_old.jsonl','rto32+g0(new rtl)'),('results/s19/rto_global_def.jsonl','default')]:
    try:
        for l in open(f):
            if l.startswith('{'): r=json.loads(l); d[(r['case'],tag)].append(r)
    except FileNotFoundError: pass
cases=list(dict.fromkeys(k[0] for k in d)); tags=list(dict.fromkeys(k[1] for k in d))
print("| case | "+" | ".join(tags)+" |"); print("|---|"+"---:|"*len(tags))
for c in cases:
    cells=[]
    for t in tags:
        v=d.get((c,t))
        cells.append(f"{round(S.mean(x['cycles'] for x in v)):,}"+("" if all(x['ok'] for x in v) else " FAIL")+f" ({round(S.mean(x['msgs'] for x in v))} msgs)" if v else "")
    print(f"| {c} | "+" | ".join(cells)+" |")
