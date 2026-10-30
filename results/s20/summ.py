import json,collections,statistics as S,sys
d=collections.defaultdict(list); bad=collections.defaultdict(list); m=collections.defaultdict(list)
for l in open(sys.argv[1] if len(sys.argv)>1 else 'rtl1.jsonl'):
    if l.startswith('{'):
        r=json.loads(l); k=(r.get('rsv'),r['case'])
        if r['ok']: d[k].append(r['cycles']); m[k].append(r['msgs'])
        else: bad[k].append(r['seed'])
for k in sorted(set(d)|set(bad), key=str): print(k,len(d[k]),bad[k],round(S.mean(d[k])) if d[k] else None, round(S.mean(m[k])) if m[k] else None)
