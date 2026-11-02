"""Step 30: certifiable N with the joint loads (W_nodes, B_vars, hull) vs step 29 (B_nodes, B_vars), and the task-stack
bound Q = max(n + 2v) + A + 1 (omega/joint.py, SPEC §7.9).  Closed forms are fitted (exact Berlekamp-Massey with held-out
terms, omega/symbolic.find_exact) to the per-N values in seqs.json; sort / qsort_l keep their step-27 worst-case B box
(no worst case over inputs is known for W_nodes or A).  Writes cert_table.json."""
import sys, json, os
sys.setrecursionlimit(100000)
from fractions import Fraction as F
from omega import symbolic, joint, placement
HERE = os.path.dirname(__file__)
seqs = json.load(open(os.path.join(HERE, "seqs.json")))
old = json.load(open(os.path.join(HERE, "..", "s29", "cert_table.json")))
bench = {"sum": 1000, "fact": 20, "list": 120, "higher": 100, "fib": 20, "treesum": 9, "treesum_direct": 14, "sort": 20, "qsort_l": 40}
MESH = [("1x1", 1, 1, None), ("2x2", 2, 2, 3), ("3x3", 3, 3, 3), ("3x3 rgrad 4", 3, 3, 4), ("4x4", 4, 4, 3), ("4x4 rgrad 6", 4, 4, 6), ("8x8 rgrad 7", 8, 8, 7)]
SS = (1024, 4096, 65536)
worst = {"sort": (lambda N: F(29, 2) * N * N + F(139, 2) * N + 24, lambda N: F(27, 2) * N * N + F(121, 2) * N + 20),
         "qsort_l": (lambda N: 32 * N * N + 86 * N + 17, lambda N: F(59, 2) * N * N + F(141, 2) * N + 15)}


def fit(seq):
    cf = symbolic.find_exact(seq)
    if cf is None: return None, None
    def ev(N, cf=cf, seq=seq):
        if N < len(seq): return F(seq[N])
        return F(cf(N))
    return ev, cf.text()


out = {}
for p in bench:
    row = {"bench_N": bench[p]}
    if p in worst:
        bn, bv = worst[p]
        L = lambda N: joint.box(int(bn(N)), int(bv(N)))
        row["forms"] = {"W_nodes": "worst-case B_nodes (step 27)", "B_vars": "worst-case B_vars"}
    else:
        rows = seqs[p]; Ns = sorted(int(k) for k in rows)
        assert Ns == list(range(len(Ns)))
        keys = {"W_nodes": [rows[str(N)]["W_nodes"] for N in Ns], "B_vars": [rows[str(N)]["B_vars"] for N in Ns],
                "atoms": [rows[str(N)]["atoms"] for N in Ns], "Q": [rows[str(N)]["Q"] for N in Ns]}
        lams = [l for l, _ in rows["0"]["hull"]]
        for i, l in enumerate(lams):
            keys[f"phi {l}"] = [F(rows[str(N)]["hull"][i][1]) * 8 for N in Ns]
        fits = {k: fit(v) for k, v in keys.items()}
        row["forms"] = {k: (f[1] if f[1] else "no exact recurrence") for k, f in fits.items() if not k.startswith("phi")}
        box_hull = all(F(rows[str(N)]["hull"][i][1]) == F(l) * rows[str(N)]["W_nodes"] + rows[str(N)]["B_vars"]
                       for N in Ns for i, l in enumerate(lams))
        row["hull_is_box"] = box_hull
        missing = [k for k, f in fits.items() if f[0] is None]
        row["missing"] = missing

        def L(N, fits=fits, lams=lams):
            ev = lambda k: fits[k][0](N)
            hull = [(F(l), ev(f"phi {l}") / 8) for l in lams if fits[f"phi {l}"][0] is not None]
            d = {"W_nodes": int(ev("W_nodes")), "B_vars": int(ev("B_vars")), "hull": hull}
            d["Q"] = int(ev("Q")) if fits["Q"][0] else None
            d["atoms"] = int(ev("atoms")) if fits["atoms"][0] else None
            return d
    row["nmax"] = {}
    for name, W, H, r in MESH:
        for S in SS:
            ok = lambda N: joint.memory_ok(W, H, L(N), S, r=r)
            hi = 1
            while ok(hi) and hi < 10**6: hi *= 2
            lo = hi // 2 if hi > 1 else 0
            if lo == 0 and not ok(0): N = -1
            else:
                while hi - lo > 1:
                    mid = (lo + hi) // 2
                    if ok(mid): lo = mid
                    else: hi = mid
                N = lo
            row["nmax"][f"{name} S={S}"] = N
    Lb = L(bench[p])
    row["bench_L"] = (Lb["W_nodes"], Lb["B_vars"]); row["bench_Q"] = Lb.get("Q")
    row["bench_min_S"] = {name: joint.min_slots(W, H, Lb, r=r) for name, W, H, r in MESH}
    Lbox = dict(Lb, hull=[])
    row["bench_min_S_nohull"] = {name: joint.min_slots(W, H, Lbox, r=r) for name, W, H, r in MESH}
    row["s29_min_S"] = old[p]["bench_min_S"]; row["s29_nmax"] = old[p]["nmax"]
    out[p] = row
    print(p, row["forms"], {True: "| box", False: "| hull below box", None: "| worst-case box"}[row.get("hull_is_box")], "| bench", bench[p], row["bench_L"], "Q", row["bench_Q"],
          "| min S", row["bench_min_S"], "| no hull", row["bench_min_S_nohull"], "| s29", row["s29_min_S"], flush=True)
json.dump(out, open(os.path.join(HERE, "cert_table.json"), "w"), indent=1, default=str)
