# step 20: fill readme_section.md -> readme_section_filled.md
import json,collections,statistics as S,re
s=open('readme_section.md').read()
ft=open('ftable.md').read().strip()
ft=ft.replace("| def |","| step 19 (`rsv=4`) |").replace("| rsv1 |","| **rsv1 (step 20)** |")
s=s.replace("{FTABLE}",ft)
# all three off
for l in open('sw4.jsonl'):
    if l.startswith('{'):
        d=json.loads(l)
        if d['tag']=='rsv0rgm0rg2off' and d['case'].startswith('treesum(9)'): s=s.replace("{R0OFF}",f"{len(d['livelock'])} / 20")
d=collections.defaultdict(list); bad=collections.defaultdict(list); m=collections.defaultdict(list)
for l in open('rtl1.jsonl'):
    if l.startswith('{'):
        r=json.loads(l)
        if r['rsv']!=1: continue
        k=r['case']
        if r['ok']: d[k].append(r['cycles']); m[k].append(r['msgs'])
        else: bad[k].append(r['seed'])
s19={"fib(12) 3x3":(15190,14951,14916,6),"treesum(6) 3x3":(5880,5824,6098,10),"list(20) 3x2":(3592,3021,3236,176),"qsort(15) 4x4":(12107,11607,11542,29),
     "sort(10) 3x3":(4113,3828,3761,21),"fib(12) 6x6":(15161,12913,13917,734),"qsort(15) 6x6":(12584,11728,11653,33),"treesum(7) 8x8":(28003,8436,7685,5359)}
rows=["| case | `+rto=32 +rgrad=0` (step 18) | `+rto=8 +rgrad=0` | step 19 (`+rsv=4`) | **step 20 (`+rsv=1`)** | Δ vs step 19 | Δ vs step 18 |","|---|---:|---:|---:|---:|---:|---:|"]
oth=0; othn=0
for k,(a,b,c,mm) in s19.items():
    if not d[k] and not bad[k]: rows.append(f"| {k} | {a:,} | {b:,} | {c:,} · {mm:,} msgs | (not run) | | |"); continue
    v=round(S.mean(d[k])); n=len(d[k])+len(bad[k])
    st=f" (**{len(bad[k])}/{n} stuck**)" if bad[k] else ""
    rows.append(f"| {k} | {a:,} | {b:,} | {c:,} · {mm:,} msgs | {v:,} · {round(S.mean(m[k])):,} msgs [{n}]{st} | {100*(v-c)/c:+.1f}% | {100*(v-a)/a:+.1f}% |")
    if k!="treesum(7) 8x8": oth+=len(bad[k]); othn+=n
s=s.replace("{RTABLE}","\n".join(rows))
k="treesum(7) 8x8"; n=len(d[k])+len(bad[k])
s=s.replace("{T7LL}",f"{len(bad[k])}/{n}" if n else "(not run)")
s=s.replace("{OTHLL}",f"{oth}/{othn}")
try:
    s=s.replace("{IDLINE}",open('idcmp.txt').readline().strip()+" (`results/s20/id_4x4.jsonl`, `id_8x8.jsonl`, `idcmp.txt`).")
except FileNotFoundError: pass
open('readme_section_filled.md','w').write(s)
print([x for x in re.findall(r"\{[A-Z0-9]+\}",s)])
