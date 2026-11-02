"""Step 30: per-N joint loads (W_nodes, B_vars, atoms A, hull Phi(lam), stack bound Q) for the suite, written to
results/s30/seqs.json; cert_table.py fits closed forms to them.  usage: seqs.py [prog ...]"""
import sys, json, time, os
sys.setrecursionlimit(200000)
from omega import joint, eal, progs
NMAX = {"sum": 40, "fact": 30, "list": 30, "higher": 30, "fib": 16, "treesum": 9, "treesum_direct": 12, "sort": 12}
BUDGET = 25.0
out_p = "results/s30/seqs.json"
data = json.load(open(out_p)) if os.path.exists(out_p) else {}
for p in (sys.argv[1:] or list(NMAX)):
    rows = data.get(p, {})
    for N in range(0, NMAX[p] + 1):
        if str(N) in rows: continue
        t = time.time()
        bk = progs.book(p, N)
        L = joint.loads(bk); b = eal.bound(bk)
        rows[str(N)] = {"B_nodes": b["B_nodes"], "B_vars": b["B_vars"], "W_nodes": L["W_nodes"], "atoms": L["atoms"],
                        "Q": L["Q"], "events": L["events"], "hull": [[str(l), str(v)] for l, v in L["hull"]],
                        "interactions": b["interactions"]}
        data[p] = rows
        json.dump(data, open(out_p, "w"), indent=0)
        print(p, N, rows[str(N)]["W_nodes"], rows[str(N)]["B_vars"], rows[str(N)]["atoms"], rows[str(N)]["Q"],
              f"{time.time() - t:.1f}s", flush=True)
        if time.time() - t > BUDGET: break
