"""Step 25 tests: symbolic B(N) (omega/symbolic.py), the var causal bound W_vars (omega/causal.py) and memory-bound
admission control on the multi-tenant fabric model (omega/admission.py).

* symbolic suite: B_nodes(N), B_vars(N) of the 8 Ω-L suite programs (+ sort with a descending / ascending input);
  every value of the closed form is compared with an independent counting run on the fitted range and on N
  beyond it (exact forms must be equal there, envelopes >= on their range);
* symbolic fuzz: random Ω-L programs (tests/test_eal.py's generator) with one size argument replaced by N;
* W_vars: >= the var peak of the lifo / fifo / 12 random semantic orders, <= B_vars; W_nodes = step 24's;
* admission: a flood of jobs that stalls the fabric without admission (status "stall", no tenant finishes) and
  completes with it (W and B reservations), a never-admissible job rejected while the others complete, a job that
  waits for the others, an untyped job passing through; each admitted run is audited every cycle (live <=
  reserved, every cell keeps the margin free) and every result is checked against the program's known answer;
* --mutants: OMEGA_EAL_MUT 8-13 must each fail.

usage: test_s25.py [--fuzz K] [--quick] [--mutants] [--json FILE]
"""
import sys, os, random, time, json, re, subprocess
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
from omega import eal, lang, progs, symbolic, causal, admission, semantic
from omega.ports import *

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
SUITE = {"fib": 20, "sum": 40, "fact": 40, "list": 40, "higher": 40, "treesum": 12, "treesum_direct": 14, "sort": 40}
EXACT = set(SUITE) - {"sort"}
BEYOND = {"fib": 2, "sum": 4, "fact": 4, "list": 4, "higher": 4, "treesum": 1, "treesum_direct": 2, "sort": 0}
passed = failed = 0
out = {"symbolic": {}, "fuzz": {}, "wvars": {}, "admission": {}}


def ok(cond, msg):
    global passed, failed
    if cond: passed += 1
    else:
        failed += 1; print("FAIL", msg, flush=True)
    return cond


def check_symbolic(label, src_of, nmax, beyond, want_exact, verbose=True):
    res = symbolic.analyse(src_of, nmax)
    if not ok(res["ok"], f"{label}: not in Ω-L ({res.get('reason')})"): return None
    lo, hi = res["range"]
    rec = {"range": [lo, hi]}
    for key in ("nodes", "vars"):
        r = res[key]
        if not ok(r is not None, f"{label}: no closed form / envelope for B_{key}"): continue
        if want_exact is not None:
            ok(r["exact"] == want_exact, f"{label}: B_{key} exact = {r['exact']}, expected {want_exact}")
        k = 1 if key == "nodes" else 2
        Ns = list(range(lo, hi + 1)) + (list(range(hi + 1, hi + 1 + beyond)) if r["exact"] else [])
        worst = 1.0
        for N in Ns:
            c = eal.count_run(lang.compile_book(src_of(N)))["B_" + key]
            v = symbolic.evaluate(res, key, N)
            if r["exact"]:
                ok(v == c, f"{label}: B_{key}({N}) = {v} from the closed form, counted {c}")
            else:
                ok(v >= c, f"{label}: envelope B_{key}({N}) = {v} < counted {c}")
            worst = max(worst, v / c if c else 1.0)
        rec[key] = {"formula": r["formula"], "start": r["start"], "exact": r["exact"], "checked": [Ns[0], Ns[-1]],
                    "max_ratio": round(worst, 3), "mean_ratio": round(r["mean_ratio"], 3), "legend": r["legend"]}
    if verbose:
        print(f"  {label}: N {lo}..{hi} (+{beyond} beyond): nodes {rec.get('nodes', {}).get('formula')} | "
              f"vars {rec.get('vars', {}).get('formula')}  [{'exact' if rec.get('nodes', {}).get('exact') else 'envelope'}]", flush=True)
    return rec


def symbolic_units():
    """find_exact on synthetic sequences: whatever it returns must reproduce every term (a short fit on the first
    terms alone would not: linear for N < 8, then quadratic; a Fibonacci-like sequence with a transient)."""
    seqs = {"linear_then_quadratic": [3 * n + 1 + (max(0, n - 7)) ** 2 for n in range(30)],
            "fib_transient": [5, 1, 9] + [0] * 25, "pow3_plus_n": [3 ** n + n for n in range(20)]}
    f = seqs["fib_transient"]
    for i in range(3, len(f)): f[i] = f[i - 1] + f[i - 2] + 2
    for name, sq in seqs.items():
        cf = symbolic.find_exact(sq)
        ok(cf is None or all(cf(N) == sq[N] for N in range(cf.start, len(sq))), f"find_exact {name}: a form that disagrees with a term")
    cf = symbolic.find_exact(seqs["pow3_plus_n"])
    ok(cf is not None and cf.text() == "3^N + N", f"find_exact pow3_plus_n: {cf and cf.text()}")
    cf = symbolic.find_exact(seqs["fib_transient"])
    ok(cf is not None and cf.start <= 2, f"find_exact fib_transient: {cf and (cf.text(), cf.start)}")


def symbolic_suite(quick=False):
    symbolic_units()
    print("symbolic B(N): suite", flush=True)
    for name, nmax in SUITE.items():
        if quick: nmax = min(nmax, 14 if name not in ("treesum", "treesum_direct", "fib") else 10)
        out["symbolic"][name] = check_symbolic(name, symbolic.program_src(name), nmax, 0 if quick else BEYOND[name],
                                               name in EXACT)
    for f, ex in (("sort_desc", True), ("sort_asc", True)):
        p = os.path.join(ROOT, "results", "s25", f + ".olm")
        if os.path.exists(p):
            out["symbolic"][f] = check_symbolic(f, symbolic.file_src(p), 20 if quick else 40, 0 if quick else 3, ex)


# ------------------------------------------------------------------------------------ symbolic fuzz
SIZE_ARGS = ("gen", "tgen", "nrec", "nlin")


def param_program(rng):
    import test_eal
    for _ in range(50):
        src, used = test_eal.gen_program(rng)
        main = src.strip().splitlines()[-1]
        occ = [m for m in re.finditer(r"\b(gen|tgen|nrec|nlin)\((\d+),", main)]
        if not occ: continue
        m = rng.choice(occ)
        newmain = main[:m.start(2)] + "N" + main[m.end(2):]
        body = src.strip().splitlines()[:-1]
        text = "\n".join(body + [newmain]) + "\n"
        return (lambda N, t=text: re.sub(r"\bN\b", str(N), t)), m.group(1), text
    return None


def symbolic_fuzz(K, seed=2525):
    print(f"symbolic B(N): fuzz {K}", flush=True)
    rng = random.Random(seed)
    stats = {"exact": 0, "envelope": 0, "none": 0, "programs": 0, "by_size_arg": {}}
    for i in range(K):
        p = param_program(rng)
        if p is None: continue
        src_of, arg, text = p
        nmax = {"gen": 30, "nlin": 30, "tgen": 9, "nrec": 14}[arg]
        f0, p0 = failed, passed
        res = symbolic.analyse(src_of, nmax, budget=1.5)
        stats["programs"] += 1
        if not ok(res["ok"], f"fuzz {i}: rejected: {res.get('reason')}"): continue
        lo, hi = res["range"]
        kinds = []
        for key in ("nodes", "vars"):
            r = res[key]
            if r is None: kinds.append("none"); continue
            kinds.append("exact" if r["exact"] else "envelope")
            Ns = list(range(lo, hi + 1)) + ([hi + 1] if r["exact"] else [])
            for N in Ns:
                c = eal.count_run(lang.compile_book(src_of(N)))["B_" + key]
                v = symbolic.evaluate(res, key, N)
                if r["exact"]: ok(v == c, f"fuzz {i} ({arg}): B_{key}({N}) closed form {v}, counted {c}\n{text}")
                else: ok(v >= c, f"fuzz {i} ({arg}): envelope B_{key}({N}) {v} < counted {c}\n{text}")
        k = "exact" if all(x == "exact" for x in kinds) else "none" if "none" in kinds else "envelope"
        stats[k] += 1
        stats["by_size_arg"].setdefault(arg, {}).setdefault(k, 0)
        stats["by_size_arg"][arg][k] += 1
    print(f"  {stats['programs']} programs: exact {stats['exact']}, envelope {stats['envelope']}, none {stats['none']}; "
          f"by size argument {stats['by_size_arg']}", flush=True)
    out["fuzz"] = stats


# ------------------------------------------------------------------------------------------- W_vars
WV = [("fib", 8), ("sum", 40), ("fact", 12), ("list", 12), ("sort", 10), ("higher", 12), ("treesum", 5), ("treesum_direct", 6)]


def wvars(quick=False):
    print("causal bound W_vars", flush=True)
    for name, N in WV[:4] if quick else WV:
        book = progs.book(name, N)
        w = causal.bound(book); b = eal.bound(book)
        pk = max(eal.count_run(book, o, s)["peak_vars"] for o, s in [("lifo", None), ("fifo", None)] +
                 [("random", s) for s in range(4 if quick else 12)])
        pkn = max(eal.count_run(book, "random", s)["peak_nodes"] for s in range(4 if quick else 12))
        ok(w["readback"] == progs.expected(name, N), f"W_vars {name}({N}): readback")
        ok(pk <= w["W_vars"] <= b["B_vars"], f"W_vars {name}({N}): peak {pk} <= W_vars {w['W_vars']} <= B_vars {b['B_vars']}")
        ok(pkn <= w["W_nodes"] <= b["B_nodes"], f"W_nodes {name}({N}): peak {pkn} <= W_nodes {w['W_nodes']} <= B_nodes {b['B_nodes']}")
        out["wvars"][f"{name}({N})"] = {"B_vars": b["B_vars"], "W_vars": w["W_vars"], "max_random_peak_vars": pk,
                                         "B_nodes": b["B_nodes"], "W_nodes": w["W_nodes"], "frees_with_causal_max": w["freed_exact"]}
        print(f"  {name}({N}): vars peak {pk} <= W {w['W_vars']} <= B {b['B_vars']} (B/W {b['B_vars'] / w['W_vars']:.2f}); "
              f"nodes W {w['W_nodes']} B {b['B_nodes']}", flush=True)


# ---------------------------------------------------------------------------------------- admission
SMALL = [("sum", 30), ("fib", 5), ("treesum_direct", 4), ("treesum", 3), ("higher", 4), ("fact", 20)]
TINY = [("fib", 5), ("treesum_direct", 4), ("fact", 12), ("sum", 10), ("fib", 4), ("treesum_direct", 3)]


def run_jobs(specs, W, H, S, admit, bound="W", audit=True, owners=None):
    jobs = [admission.Job(f"{n}({N})", progs.source(n, N), (owners[k] if owners else k % 15), bound=bound)
            for k, (n, N) in enumerate(specs)]
    t = time.time()
    sch = admission.Scheduler(jobs, W, H, S, admit=admit)
    r = sch.run(audit=audit)
    r["correct"] = sum(1 for j, (n, N) in zip(r["jobs"], specs) if j["result"] == progs.expected(n, N))
    r["wrong"] = sum(1 for j, (n, N) in zip(r["jobs"], specs) if j["result"] is not None and j["result"] != progs.expected(n, N))
    r["secs"] = round(time.time() - t, 1)
    return r, sch


def summary(r):
    return {k: r[k] for k in ("status", "error", "violation", "cycles", "interactions", "peak_live", "max_reserved", "budget",
                              "correct", "wrong", "secs")} | {"n": len(r["jobs"]),
            "states": {s: sum(1 for j in r["jobs"] if j["state"] == s) for s in ("done", "running", "rejected", "new")}}


def admission_tests(quick=False):
    print("admission control (fabric model)", flush=True)
    A = out["admission"]
    # 1. flood: 180 jobs of 15 owners on 2x2 x 280 slots.  Loaded at once (step 24) the fabric runs out of memory
    # and stops (no tenant finishes); with admission every job finishes with its known answer.
    flood = (SMALL * 30)[:180]
    r0, _ = run_jobs(flood, 2, 2, 280, admit=False)
    A["flood_no_admission"] = summary(r0)
    ok(r0["status"] in ("stall", "error") and r0["wrong"] == 0, f"flood without admission: expected a stall, got {r0['status']} ({r0['correct']} correct)")
    for bound in (("W",) if quick else ("W", "B")):
        r1, sch = run_jobs(flood, 2, 2, 280, admit=True, bound=bound)
        A[f"flood_admission_{bound}"] = summary(r1)
        adm = [j for j in sch.jobs if j.state != "rejected"]
        rej = [j for j in sch.jobs if j.state == "rejected"]
        ok(all(j.need[0] > sch.budget[0] or j.need[1] > sch.budget[1] for j in rej), f"flood ({bound}): a job that fits was rejected")
        ok(r1["status"] == "ok" and r1["correct"] == len(adm) and r1["violation"] is None,
           f"flood with admission ({bound}): {r1['status']} {r1['correct']}/{len(adm)} {r1['violation']}")
        if bound == "W": ok(not rej, "flood (W): every job fits its W reservation")
        print(f"  flood 180 jobs, 2x2 x 280: without admission {r0['status']} after {r0['cycles']} cycles "
              f"({r0['correct']} finished); with admission ({bound}) {r1['status']}, {r1['correct']}/{len(adm)} admitted jobs correct, "
              f"{len(rej)} rejected (bound > budget), {r1['cycles']} cycles, peak live {r1['peak_live']}, "
              f"max reserved {r1['max_reserved']} of {r1['budget']}", flush=True)
    # 2. flood on 3x3 x 280 with 300 jobs
    if not quick:
        fl2 = (SMALL * 50)[:300]
        r0, _ = run_jobs(fl2, 3, 3, 280, admit=False)
        r1, _ = run_jobs(fl2, 3, 3, 280, admit=True)
        A["flood3_no_admission"] = summary(r0); A["flood3_admission_W"] = summary(r1)
        ok(r0["status"] in ("stall", "error") and r0["wrong"] == 0, f"flood 3x3 without admission: expected a stall, got {r0['status']}")
        ok(r1["status"] == "ok" and r1["correct"] == len(fl2) and r1["violation"] is None,
           f"flood 3x3 with admission: {r1['status']} {r1['correct']}/{len(fl2)} {r1['violation']}")
        print(f"  flood 300 jobs, 3x3 x 280: without admission {r0['status']} after {r0['cycles']} cycles ({r0['correct']} finished, "
              f"peak live {r0['peak_live']}); with admission {r1['status']}, {r1['correct']}/300 correct, {r1['cycles']} cycles", flush=True)
    # 3. never admissible: treesum(9) (W_nodes 7,166) on 2x2 x 200 is rejected at submission, the others all finish
    sp = [("treesum", 9)] + TINY * 3
    r1, _ = run_jobs(sp, 2, 2, 200, admit=True)
    A["reject"] = summary(r1)
    ok(r1["jobs"][0]["state"] == "rejected" and r1["status"] == "ok" and r1["correct"] == len(sp) - 1 and r1["violation"] is None,
       f"reject: {r1['jobs'][0]['state']} {r1['status']} {r1['correct']}/{len(sp) - 1}")
    # 4. waits for room: treesum(5) needs (446, 1005) of a 1,072 budget, so the jobs behind it wait until it is done
    sp = [("treesum", 5)] + SMALL * 3
    r1, sch = run_jobs(sp, 2, 2, 1100, admit=True)
    A["queue"] = summary(r1)
    t5 = r1["jobs"][0]["end"]
    ok(r1["status"] == "ok" and r1["correct"] == len(sp) and r1["violation"] is None and
       all(j["start"] >= t5 for j in r1["jobs"][1:]), f"queue: {r1['status']} {r1['correct']}/{len(sp)}, starts after {t5}")
    # 5. untyped job (qsort is not in Ω-L) passes through unreserved; the typed ones are admitted around it
    sp = [("qsort", 8)] + SMALL * 2
    r1, _ = run_jobs(sp, 2, 2, 280, admit=True)
    A["untyped"] = summary(r1)
    ok(not r1["jobs"][0]["typed"] and r1["jobs"][0]["start"] == 0 and r1["status"] == "ok" and r1["correct"] == len(sp),
       f"untyped: {r1['status']} {r1['correct']}/{len(sp)}")
    # 6. one cell: admission keeps sum of bounds <= slots (no margin)
    sp = TINY * 4
    r1, _ = run_jobs(sp, 1, 1, 150, admit=True)
    A["one_cell"] = summary(r1)
    ok(r1["status"] == "ok" and r1["correct"] == len(sp) and r1["violation"] is None, f"1x1: {r1['status']} {r1['correct']}/{len(sp)} {r1['violation']}")
    print(f"  reject / queue / untyped / 1x1: {A['reject']['status']}, {A['queue']['status']}, {A['untyped']['status']}, {A['one_cell']['status']}", flush=True)


# ------------------------------------------------------------------------------------------ mutants
MUTANTS = {8: "find_exact skips the held-out terms", 9: "envelope skips its feasibility checks",
           10: "W_vars frees a var at the first event of F_v", 11: "admission ignores the running jobs",
           12: "reservations never released", 13: "reserve the depth-first peak instead of a bound"}


def mutants():
    caught = 0
    for m, what in MUTANTS.items():
        sec = {8: "--only-symbolic", 9: "--only-symbolic", 10: "--only-wvars"}.get(m, "--only-admission")
        env = dict(os.environ, OMEGA_EAL_MUT=str(m), PYTHONPATH=f"{ROOT}:{HERE}")
        p = subprocess.run([sys.executable, __file__, "--quick", sec], env=env, capture_output=True, text=True, timeout=3000)
        c = p.returncode != 0
        caught += c
        print(f"  mutant {m} ({what}): {'caught' if c else 'NOT caught'}", flush=True)
    ok(caught == len(MUTANTS), f"mutants: {caught}/{len(MUTANTS)} caught")
    print(f"s25 mutants: {caught}/{len(MUTANTS)} caught", flush=True)


def main(argv):
    t0 = time.time()
    quick = "--quick" in argv
    if "--mutants" in argv:
        mutants(); return 0 if failed == 0 else 1
    only = [a for a in argv if a.startswith("--only-")]
    K = int(argv[argv.index("--fuzz") + 1]) if "--fuzz" in argv else (6 if quick else 40)
    if not only or "--only-symbolic" in only:
        symbolic_suite(quick)
        symbolic_fuzz(K)
    if not only or "--only-wvars" in only: wvars(quick)
    if not only or "--only-admission" in only: admission_tests(quick)
    if "--json" in argv:
        with open(argv[argv.index("--json") + 1], "w") as f: json.dump(out, f, indent=1, default=str)
    print(f"step 25 tests: {passed}/{passed + failed} pass ({time.time() - t0:.0f}s)")
    return 0 if failed == 0 else 1


MUT = eal.MUT
if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
