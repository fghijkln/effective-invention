# step 20: fabric probe table (sw1/sw2/sw4/sw6) -> markdown
import json
rows={}; order=[]
for f in ['sw1.jsonl','sw2.jsonl','sw4.jsonl','sw6.jsonl']:
    for l in open(f):
        if not l.startswith('{'): continue
        d=json.loads(l); k=d['tag']
        if k not in rows: rows[k]={}; order.append(k)
        rows[k][(d['case'],d['seeds'])]=(len(d['livelock']),d['cycles'],len(d['cyc'])+len(d['livelock']))
cols=[('treesum(6) 3x3','1-20'),('list(20) 3x2','1-20'),('fib(12) 6x6','1-20'),('treesum(9) 3x3','1-20')]
print("| config | "+" | ".join(f"{c} ({s})" for c,s in cols)+" |"); print("|---|"+"---:|"*len(cols))
for k in order:
    if not any(c in rows[k] for c in cols): continue
    cells=[]
    for c in cols:
        v=rows[k].get(c); cells.append("–" if v is None else (f"{v[1]:,}" if c[0]!='treesum(9) 3x3' else f"**{v[0]}/{v[2]}** livelock" if v[0] else f"0/{v[2]} · {v[1]:,}"))
    print(f"| {k} | "+" | ".join(cells)+" |")
