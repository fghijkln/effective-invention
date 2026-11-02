"""Step 29: largest N certified per cell size S on 1x1 (step 28 rule) and on meshes (placement certificate,
omega/placement.py, or the step-28 mesh rule, whichever is better), from the closed forms of §7.3 / §7.6 (worst case
over inputs for sort / qsort_l), and the smallest S per mesh for the benchmark sizes."""
import sys, json
sys.setrecursionlimit(100000)
from omega import symbolic, placement
progs = ["sum", "fact", "list", "higher", "fib", "treesum", "treesum_direct", "sort"]
src = {p: symbolic.program_src(p) for p in progs}
src["qsort_l"] = symbolic.file_src("programs/qsort_l.olm")
bench = {"sum": 1000, "fact": 20, "list": 120, "higher": 100, "fib": 20, "treesum": 9, "treesum_direct": 14, "sort": 20, "qsort_l": 40}
# sort / qsort_l: worst case over all inputs of length N (SPEC 7.3 / 7.6), as polynomials
from fractions import Fraction as F
worst = {"sort": (lambda N: F(29, 2) * N * N + F(139, 2) * N + 24, lambda N: F(27, 2) * N * N + F(121, 2) * N + 20),
         "qsort_l": (lambda N: 32 * N * N + 86 * N + 17, lambda N: F(59, 2) * N * N + F(141, 2) * N + 15)}
MESH = [("1x1", 1, 1, None), ("2x2", 2, 2, 3), ("3x3", 3, 3, 3), ("3x3 rgrad 4", 3, 3, 4), ("4x4", 4, 4, 3), ("4x4 rgrad 6", 4, 4, 6), ("8x8 rgrad 7", 8, 8, 7)]
SS = (1024, 4096, 65536)
out = {}
for p, f in src.items():
    if p in worst:
        bn, bv = worst[p]; Bn = lambda N: int(bn(N)); Bv = lambda N: int(bv(N))
        form = ("worst " + p, "")
    else:
        res = symbolic.analyse(f, Nmax=30 if p not in ("fib", "treesum", "treesum_direct") else 14, budget=3.0)
        Bn = lambda N, res=res: int(symbolic.evaluate(res, "nodes", N)); Bv = lambda N, res=res: int(symbolic.evaluate(res, "vars", N))
        form = (res["nodes"]["formula"], res["vars"]["formula"])
    row = {"B_nodes": form[0], "B_vars": form[1], "nmax": {}, "bench_N": bench[p], "bench_B": (Bn(bench[p]), Bv(bench[p])), "bench_min_S": {}}
    for name, W, H, r in MESH:
        for S in SS:
            ok = lambda N: placement.certified(W, H, Bn(N), Bv(N), S, r=r)
            hi = 1
            while ok(hi) and hi < 10**7: hi *= 2
            lo = hi // 2 if hi > 1 else 0          # ok(lo) (or lo = 0), not ok(hi); B is increasing in N
            if lo == 0 and not ok(0): N = -1
            else:
                while hi - lo > 1:
                    mid = (lo + hi) // 2
                    if ok(mid): lo = mid
                    else: hi = mid
                N = lo
            row["nmax"][f"{name} S={S}"] = N
        row["bench_min_S"][name] = placement.min_slots(W, H, Bn(bench[p]), Bv(bench[p]), r=r)
    out[p] = row
    print(p, row["B_nodes"], "|", " ".join(f"{k}:{v}" for k, v in row["nmax"].items()), "| bench", bench[p], row["bench_B"], row["bench_min_S"], flush=True)
json.dump(out, open("results/s29/cert_table.json", "w"), indent=1)
