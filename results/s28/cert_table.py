"""Step 28: largest input size N certified on one cell of S slots (B_nodes(N), B_vars(N) <= S) from the step-25/27
closed forms (omega.symbolic), for S = 1,024 (default), 4,096 (largest before step 28) and 65,536 (step 28)."""
import sys, json
sys.setrecursionlimit(100000)
from omega import symbolic
progs = ["sum", "fact", "list", "higher", "fib", "treesum", "treesum_direct", "sort"]
src = {p: symbolic.program_src(p) for p in progs}
src["qsort_l"] = symbolic.file_src("programs/qsort_l.olm")
bench = {"sum": 1000, "fact": 20, "list": 120, "higher": 100, "fib": 20, "treesum": 9, "treesum_direct": 14, "sort": 20, "qsort_l": 40}
out = {}
for p, f in src.items():
    res = symbolic.analyse(f, Nmax=30 if p not in ("fib", "treesum", "treesum_direct") else 14, budget=3.0)
    if not res["ok"] or res["nodes"] is None or res["vars"] is None:
        print(p, "no closed form", flush=True); continue
    need = lambda N: max(symbolic.evaluate(res, "nodes", N), symbolic.evaluate(res, "vars", N))
    row = {"nodes": res["nodes"]["formula"], "vars": res["vars"]["formula"], "exact": res["nodes"]["exact"] and res["vars"]["exact"]}
    for S in (1024, 4096, 65536):
        N = 0
        while need(N + 1) <= S and N < 10**6: N += 1
        row[S] = N
    row["bench_N"] = bench[p]; row["bench_need"] = need(bench[p])
    out[p] = row
    print(f"{p}: B_nodes {row['nodes']}, B_vars {row['vars']} ({'exact' if row['exact'] else 'envelope'}); N_max 1024: {row[1024]}, 4096: {row[4096]}, 65536: {row[65536]}; benchmark N={bench[p]} needs {row['bench_need']}", flush=True)
json.dump(out, open("results/s28/cert_table.json", "w"), indent=1)
