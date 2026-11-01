"""Step 27 tests: qsort in Ω-L (programs/qsort_l.olm; programs/qsort.olm unchanged).

* Ω-L: qsort_l is accepted (qs: numeric fuel recursion, part / app: structural), qsort is still rejected (rule A);
* correctness: qsort_l == qsort == Python's sorted checksum on the semantic reducer (N = 0..40, several seeds, ascending,
  descending and constant inputs), on the fabric model (1x1, 2x2, 4x4) and on the RTL (2x2 default, 1x1 with exactly
  B_nodes / B_vars free slots);
* bound: B (step 24) >= the node / var peaks of 5 semantic orders and of the fabric model; W_nodes, W_vars (step 25)
  between those peaks and B;
* symbolic (step 25): exact closed forms for the descending (worst case) and ascending inputs, an envelope for the
  program's own pseudo-random input, and the data decomposition B = a + b·N + c·P + d·A + e·Z (P: elements partitioned,
  A: app steps, Z: calls at fuel 0), exact on every input tried, whose maximum over all inputs of length N >= 1 is the
  descending input's closed form (so the worst-case envelope is attained).

usage: test_s27.py [--quick] [--no-rtl] [--json FILE]
"""
import sys, os, time, json, random
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "results", "s27"))
from fractions import Fraction as Fr
from omega import eal, lang, semantic, progs, symbolic, causal, fabric
import variants as V, decomp as D

passed = failed = 0
out = {}


def ok(cond, msg):
    global passed, failed
    if cond: passed += 1
    else:
        failed += 1; print("FAIL", msg, flush=True)
    return cond


def want(N, s=42, kind="rnd"):
    return f"#{progs._check(sorted(V.data(N, s, kind)))}"


def omega_l():
    r = eal.check(progs.source("qsort_l", 5))
    ok(r["ok"], f"qsort_l not in Ω-L: {r.get('reason')}")
    g = eal.growth(r.get("recursion", {})) if r["ok"] else {}
    ok("numeric" in str(g.get("qs")) and "structural" in str(g.get("part")) and "structural" in str(g.get("app")),
       f"qsort_l recursion kinds {g}")
    r0 = eal.check(progs.source("qsort", 5))
    ok(not r0["ok"] and "affine" in r0["reason"], f"qsort must stay outside Ω-L (rule A): {r0}")
    out["omega_l"] = {k: str(v) for k, v in g.items()}
    print(f"  Ω-L: qsort_l accepted ({', '.join(f'{k}: {v}' for k, v in g.items())}); qsort rejected: {r0['reason']}", flush=True)


def semantic_check(quick):
    n = 0
    for N in range(0, 41 if not quick else 16):
        cases = [("rnd", 42), ("asc", 0), ("desc", 0)] + ([("rnd", s) for s in (1, 7, 99, 1234)] if N % 3 == 0 else [])
        for kind, s in cases:
            a = semantic.result(lang.compile_book(V.src("qsort_l", N, s, kind)))
            b = semantic.result(lang.compile_book(V.src("qsort", N, s, kind)))
            w = want(N, s, kind)
            ok(a["readback"] == w and b["readback"] == w, f"semantic {kind} s={s} N={N}: qsort_l {a['readback']} qsort {b['readback']} want {w}")
            n += 1
    # constant input (all duplicates go right) and a literal list with duplicates
    for xs in ([5] * 12, [3, 1, 3, 2, 3, 1, 0, 0, 9], []):
        a = semantic.result(lang.compile_book(D.src_list(xs)))
        ok(a["readback"] == f"#{progs._check(sorted(xs))}", f"semantic literal {xs}: {a['readback']}")
        n += 1
    print(f"  semantic: qsort_l == qsort == sorted on {n} inputs", flush=True)


def interactions_compare():
    rows = []
    for N in (5, 10, 20, 40):
        a = semantic.result(progs.book("qsort_l", N)); b = semantic.result(progs.book("qsort", N))
        rows.append((N, a["interactions"], b["interactions"]))
    out["interactions_qsl_vs_qs"] = rows
    print("  interactions qsort_l / qsort: " + ", ".join(f"N={N}: {a} / {b} ({a / b:.2f}x)" for N, a, b in rows), flush=True)


def fabric_check(quick):
    for W, H, Ns in ((1, 1, (0, 1, 7, 15)), (2, 2, (3, 12, 20)), (4, 4, (20,) if quick else (20, 30))):
        for N in Ns:
            for seed in (1, 2):
                book = progs.book("qsort_l", N)
                f = fabric.Fabric(book, W, H, slots=2048, seed=seed, p_jitter=0.1 if W * H > 1 else 0.0)
                f.run()
                ok(f.readback() == progs.expected("qsort_l", N), f"fabric {W}x{H} N={N} seed {seed}: {f.readback()}")
    print("  fabric model 1x1 / 2x2 / 4x4: ok", flush=True)


def bounds(quick):
    import test_eal as TE
    rec = {}
    for N in ((4, 8) if quick else (2, 4, 8, 12)):
        book = progs.book("qsort_l", N)
        b = eal.bound(book)
        rs = TE.sem_peaks(book)
        pn = max(r["peak_nodes"] for r in rs); pv = max(r["peak_vars"] for r in rs)
        fp = TE.fabric_peak(book, 2, 2, 3)
        w = causal.bound(book)
        ok(all(r["B_nodes"] == b["B_nodes"] and r["B_vars"] == b["B_vars"] for r in rs), f"B not schedule independent at N={N}")
        ok(pn <= w["W_nodes"] <= b["B_nodes"] and pv <= w["W_vars"] <= b["B_vars"],
           f"N={N}: peaks ({pn}, {pv}) W ({w['W_nodes']}, {w['W_vars']}) B ({b['B_nodes']}, {b['B_vars']})")
        ok(fp["g_nodes"] <= b["B_nodes"] and fp["g_vars"] <= b["B_vars"] and fp["readback"] == progs.expected("qsort_l", N),
           f"N={N}: fabric 2x2 peak ({fp['g_nodes']}, {fp['g_vars']}) > B or wrong {fp['readback']}")
        rec[N] = {"B": (b["B_nodes"], b["B_vars"]), "W": (w["W_nodes"], w["W_vars"]), "sem_peak": (pn, pv),
                  "fabric2x2_peak": (fp["g_nodes"], fp["g_vars"]), "interactions": b["interactions"]}
        print(f"  N={N}: B ({b['B_nodes']}, {b['B_vars']})  W ({w['W_nodes']}, {w['W_vars']})  semantic peak ({pn}, {pv})  "
              f"fabric 2x2 peak ({fp['g_nodes']}, {fp['g_vars']})  B/W {b['B_nodes'] / w['W_nodes']:.2f} / {b['B_vars'] / w['W_vars']:.2f}", flush=True)
    out["bounds"] = rec


def symbolic_check(quick):
    nmax = 24 if quick else 40
    rec = {}
    for kind in ("desc", "asc", "rnd"):
        r = symbolic.analyse(lambda N: V.src("qsort_l", N, 42, kind), nmax)
        if not ok(r["ok"] and r["nodes"] and r["vars"], f"symbolic {kind}: {r.get('reason')}"): continue
        for key in ("nodes", "vars"):
            x = r[key]
            if kind != "rnd": ok(x["exact"], f"symbolic {kind}: B_{key} not exact ({x['formula']})")
            ok(x["sound"], f"symbolic {kind}: B_{key} below a counted value")
            if x["exact"]:                                  # held-out N past the fitted range
                for N in (nmax + 1, nmax + 2):
                    c = eal.count_run(lang.compile_book(V.src("qsort_l", N, 42, kind)))["B_" + key]
                    ok(symbolic.evaluate(r, key, N) == c, f"symbolic {kind}: B_{key}({N}) {symbolic.evaluate(r, key, N)} != counted {c}")
        rec[kind] = {k: {"formula": r[k]["formula"], "exact": r[k]["exact"], "start": r[k]["start"], "max_ratio": round(r[k]["max_ratio"], 3)}
                     for k in ("nodes", "vars")}
        print(f"  symbolic {kind}: B_nodes = {r['nodes']['formula']} | B_vars = {r['vars']['formula']}  "
              f"[{'exact' if r['nodes']['exact'] else 'envelope'}, N = 0..{nmax}]", flush=True)
    out["symbolic"] = rec
    return rec


def decomposition(quick, sym):
    rows = []
    for xs in D.inputs(10 if quick else 18):
        b = eal.count_run(lang.compile_book(D.src_list(xs)))
        P, A, Z = D.stats(xs, len(xs))
        rows.append((len(xs), P, A, Z, b["B_nodes"], b["B_vars"]))
    prog = []                                            # the program itself (rnd generator) with other seeds / orders
    for N in range(0, 26 if not quick else 12):
        for kind, s in (("rnd", 42), ("rnd", 7), ("rnd", 1234), ("asc", 0), ("desc", 0)):
            b = eal.count_run(lang.compile_book(V.src("qsort_l", N, s, kind)))
            P, A, Z = D.stats(V.data(N, s, kind), N)
            prog.append((N, P, A, Z, b["B_nodes"], b["B_vars"]))
    rec = {}
    for k, key in ((4, "nodes"), (5, "vars")):
        for label, rs in (("literal", rows), ("program", prog)):
            a, b_, c, d, e = D.fit(rs, k)
            exact = all(a + b_ * r[0] + c * r[1] + d * r[2] + e * r[3] == r[k] for r in rs)
            ok(exact, f"decomposition ({label}) B_{key} not exact")
            if label == "program":
                # worst case over inputs of length N >= 1: P <= N(N-1)/2, A <= P, Z in {0, 2} and Z = 2 only for the full
                # chain (P maximal); with c + d > 0 > e the maximum is P = A = N(N-1)/2, Z = 2 (strictly descending input)
                ok(c + d > 0 and c > 0 and e < 0 and d > 0, f"decomposition B_{key}: coefficient signs c={c} d={d} e={e}")
                worst = lambda N: a + b_ * N + (c + d) * Fr(N * (N - 1), 2) + 2 * e
                ok(all(worst(r[0]) >= r[k] for r in rs if r[0] >= 1), f"decomposition B_{key}: worst case below a counted value")
                if "desc" in sym:
                    ok(all(worst(N) == symbolic.evaluate({key: sym["desc_res"][key]}, key, N) for N in range(1, 41)) if "desc_res" in sym else True,
                       f"decomposition B_{key}: worst case differs from the descending closed form")
                A2 = (c + d) / 2; A1 = b_ - (c + d) / 2; A0 = a + 2 * e
                rec[key] = {"coeffs": [symbolic.fmt_num(v) for v in (a, b_, c, d, e)],
                            "worst": f"{symbolic.fmt_num(A2)}·N^2 + {symbolic.fmt_num(A1)}·N + {symbolic.fmt_num(A0)} (N >= 1)"}
                print(f"  decomposition B_{key} = {symbolic.fmt_num(a)} + {symbolic.fmt_num(b_)}·N + {symbolic.fmt_num(c)}·P + "
                      f"{symbolic.fmt_num(d)}·A + {symbolic.fmt_num(e)}·Z  (exact on {len(rows)} literal + {len(prog)} program inputs); "
                      f"worst case over every input of length N >= 1: {rec[key]['worst']}", flush=True)
    out["decomposition"] = rec


def rtl_check(quick):
    import test_eal as TE
    from omega import rtl
    rec = {}
    for N in ((0, 4, 8) if quick else (0, 1, 4, 8, 12)):
        book = progs.book("qsort_l", N); b = eal.bound(book)
        good, pn, pv, cyc, st = TE.rtl_at_bound(book, b, progs.expected("qsort_l", N))
        ok(good, f"RTL 1x1 with exactly B = ({b['B_nodes']}, {b['B_vars']}) slots, N={N}: status {st}")
        rec[f"1x1_B_{N}"] = {"B": (b["B_nodes"], b["B_vars"]), "rtl_peak": (pn, pv), "cycles": cyc, "status": st}
        print(f"  RTL 1x1 at B ({b['B_nodes']}, {b['B_vars']}), N={N}: status {st}, peak ({pn}, {pv}), {cyc} cycles", flush=True)
    for N in ((12,) if quick else (12, 30)):
        r1 = rtl.run(progs.book("qsort_l", N), 2, 2, seed=1, slots=1024)
        r0 = rtl.run(progs.book("qsort", N), 2, 2, seed=1, slots=1024)
        ok(r1["status"] == 0 and r1["readback"] == progs.expected("qsort_l", N) == r0["readback"], f"RTL 2x2 N={N}: {r1['readback']} vs {r0['readback']}")
        rec[f"2x2_{N}"] = {"qsort_l": (r1.get("cycles"), r1.get("interactions")), "qsort": (r0.get("cycles"), r0.get("interactions"))}
        print(f"  RTL 2x2 N={N}: qsort_l {r1.get('cycles')} cycles / {r1.get('interactions')} interactions, "
              f"qsort {r0.get('cycles')} / {r0.get('interactions')}", flush=True)
    out["rtl"] = rec


def main(argv):
    t0 = time.time()
    quick = "--quick" in argv
    print("step 27: qsort in Ω-L", flush=True)
    omega_l()
    semantic_check(quick)
    interactions_compare()
    fabric_check(quick)
    bounds(quick)
    sym = symbolic_check(quick)
    desc = symbolic.analyse(lambda N: V.src("qsort_l", N, 42, "desc"), 24 if quick else 40)
    sym["desc_res"] = desc
    decomposition(quick, sym)
    sym.pop("desc_res", None)
    if "--no-rtl" not in argv: rtl_check(quick)
    if "--json" in argv:
        with open(argv[argv.index("--json") + 1], "w") as f: json.dump(out, f, indent=1, default=str)
    print(f"step 27 tests: {passed}/{passed + failed} pass ({time.time() - t0:.0f}s)", flush=True)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
