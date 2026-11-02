import json, sys
for s in ('small', 'hetero', 'big', 'boundary'):
    try: R = [json.loads(l) for l in open(f'results/s30/val_{s}.jsonl')]
    except FileNotFoundError: continue
    cl = [r for r in R if r.get('claim')]
    un = [r for r in R if not r.get('claim')]
    print(s, len(R), 'claimed', len(cl), 'sound', sum(r['sound'] for r in cl), 'errors', sum('error' in r for r in R),
          '| uncertified', len(un), 'finished', sum(r.get('ok', False) for r in un), 'status', sorted({r.get('status') for r in un}))
    if cl:
        print('  live/L max n %.4f v %.4f, tasks/Q max %.5f, max tasks %d, max cell tasks %d, min tslack %d, hull_ok %d/%d' % (
            max(r['live_peak'][0] / r['L'][0] for r in cl), max(r['live_peak'][1] / r['L'][1] for r in cl),
            max(r['tcert_peak'] / r['Q'] for r in cl), max(r['tcert_peak'] for r in cl), max(r['tcert_cell'] for r in cl),
            min(r['tcert_slack'] for r in cl), sum(r['hull_ok'] for r in cl), len(cl)))
    for r in R:
        if r.get('claim') and not r['sound']: print('  UNSOUND', r['key'], r.get('status'), r.get('error', '')[:200])
