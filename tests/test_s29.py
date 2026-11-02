"""Step 29 tests: the placement-aware memory certificate (omega/placement.py, SPEC §7.8).

* checker: `placement.certify` (closed form for homogeneous cells, exact split search otherwise) against the
  independent brute force `placement.witness` (an explicit occupancy that leaves some rgrad-ball without a roomy
  cell) on random meshes, radii, free-slot shapes and loads; boundary loads L = k·(S - lm_hi + 1); the modes the
  certificate refuses (1x1, rgrad 0, lm_mode != 2, lm_lo < D_max); admission budgets checked against the brute force;
  the load is the §7.2 bound B (>= every semantic peak), never a measured peak;
* the certifiable-N table vs step 28 (1x1 / 2x2 / 3x3 at 1,024, 4,096, 65,536 slots) and fib(20) / treesum_direct(14)
  on 3x3 (smallest cells 52,602 / 39,384 slots);
* RTL at certified configurations (+pcert audit: zero cycles without a roomy cell within rgrad hops of every cell,
  live load <= L, right answer and interaction count): the largest N each mesh certifies at 1,024 slots for which
  one cell does not, heterogeneous ballast shapes (room only in a corner: certified at rgrad 4, not 3, and the audit
  sees the difference), fib(20) / treesum_direct(14) on 3x3 at the smallest certified cells;
* admission with the placement budgets (option, default off): fabric-model scheduler (audit of the certificate's
  conclusion every cycle) and the RTL controller agree on start order and interactions; more jobs run at once than
  with the step-25 per-cell budgets.

usage: test_s29.py [--quick | --ci] [--mutants] [--json FILE]
"""
import sys, os, time, json, random, subprocess
sys.setrecursionlimit(100000)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
from omega import eal, progs, fabric, semantic, rtl, admission, adm_rtl, placement as PL
from omega.ports import *

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
passed = failed = 0
out = {}


def ok(cond, msg):
    global passed, failed
    if cond: passed += 1
    else:
        failed += 1; print("FAIL", msg, flush=True)
    return cond


# ------------------------------------------------------------------------------------------------ checker
def checker(n=2500):
    rnd = random.Random(2911)
    bad = 0
    for i in range(n):
        W, H = rnd.choice([(2, 1), (2, 2), (3, 2), (2, 3), (3, 3), (4, 2), (4, 3)])
        r = rnd.randint(1, 5)
        S = rnd.choice([80, 100, 256, 1024])
        het = rnd.random() < 0.6
        fn = {c: rnd.choice([rnd.randint(0, 70), rnd.randint(0, S)]) for c in PL.cells(W, H)} if het else None
        fv = ({c: rnd.randint(0, S) for c in PL.cells(W, H)} if rnd.random() < 0.5 else dict(fn)) if het else None
        m = S - fabric.LM_HI + 1
        Ln = rnd.choice([rnd.randint(0, 5 * S), rnd.randint(0, 5) * m + rnd.choice((-1, 0, 1)), rnd.randint(0, 3 * S)])
        Lv = rnd.choice([rnd.randint(0, 5 * S), rnd.randint(0, 5) * m + rnd.choice((-1, 0, 1))])
        Ln, Lv = max(0, Ln), max(0, Lv)
        a = PL.certify(W, H, Ln, Lv, free_n=fn, free_v=fv, S=S, r=r)
        w = PL.witness(W, H, Ln, Lv, free_n=fn, free_v=fv, S=S, r=r)
        if a == (w is not None):
            bad += 1
            if bad <= 3: print(f"  mismatch {W}x{H} r{r} S{S} L ({Ln}, {Lv}) het {het}: certify {a}, witness {w}", flush=True)
    ok(bad == 0, f"certify vs brute-force witness: {bad}/{n} disagree")
    # boundaries: 2x2 x 1024, m = 961.  Two node-poor + two var-poor cells cost exactly (2m, 2m).
    m = 1024 - fabric.LM_HI + 1
    ok(not PL.certify(2, 2, 2 * m, 2 * m, S=1024, r=3), "2x2 load (2m, 2m) must not certify")
    ok(PL.certify(2, 2, 2 * m, 2 * m - 1, S=1024, r=3), "2x2 load (2m, 2m - 1) must certify")
    ok(PL.certify(2, 2, 3 * m + m - 1, 0, S=1024, r=3) and not PL.certify(2, 2, 4 * m, 0, S=1024, r=3), "2x2 nodes only: 4m - 1 certifies, 4m not")
    # corner room on 3x3: ball(0,0) of radius 3 misses (2,2)
    cs = PL.cells(3, 3)
    keep = {c: 8 for c in cs}; keep[(2, 2)] = 1024
    ok(not PL.certify(3, 3, 490, 388, free_n=keep, free_v=keep, S=1024, r=3) and PL.certify(3, 3, 490, 388, free_n=keep, free_v=keep, S=1024, r=4),
       "corner room: certified at rgrad 4 only")
    ok(PL.min_ball(3, 3, 3) == 8 and PL.min_ball(3, 3, 4) == 9 and PL.min_ball(4, 4, 3) == 10 and PL.min_ball(8, 8, 7) == 36, "ball sizes")
    # refused modes
    ok(not PL.certify(1, 1, 10, 10, S=1024), "1x1: no placement certificate")
    ok(not PL.certify(2, 2, 10, 10, S=1024, r=0), "rgrad 0: no certificate")
    ok(not PL.certify(2, 2, 10, 10, S=1024, lm_mode=0), "lm_mode 0: no certificate")
    ok(not PL.certify(2, 2, 10, 10, S=1024, lm_lo=8, dmax=12), "lm_lo < D_max: no certificate")
    # admission budgets: any sums within them certify (brute force), for several meshes / splits
    nb = 0
    for (W, H, r) in ((2, 2, 3), (3, 3, 3), (3, 3, 4), (4, 2, 2), (4, 3, 3)):
        for S in (300, 1024, 20000):
            for mix in ((1, 1), (3, 1), (1, 4), (1, 0)):
                b = PL.budgets(W, H, S, mix=mix, r=r)
                if b is None: continue
                nb += 1
                ok(PL.witness(W, H, b[0], b[1], S=S, r=r) is None, f"budgets {W}x{H} r{r} S{S} mix {mix}: {b} admit a coverable load")
    print(f"  checker: certify = no brute-force witness on {n} random instances; boundaries; refused modes; {nb} budget pairs sound", flush=True)


def load_is_bound():
    for name, N in (("fib", 9), ("treesum", 5), ("sum", 50), ("list", 10), ("qsort_l", 8), ("sort", 8), ("higher", 10)):
        book = progs.book(name, N)
        Ln, Lv, b = PL.job_load(book)
        ok((Ln, Lv) == (b["B_nodes"], b["B_vars"]) and Ln >= b["peak_nodes"] and Lv >= b["peak_vars"], f"{name}({N}): load {Ln, Lv} vs bound / peak")
    print("  load: the certificate charges B (>= the depth-first peak), not a measured peak", flush=True)


# ------------------------------------------------------------------------------------------------ table
TAB = os.path.join(ROOT, "results", "s29", "cert_table.json")


def table():
    tab = json.load(open(TAB))
    rows = {}
    for p, row in tab.items():
        nm = row["nmax"]
        for S in (1024, 4096, 65536):
            ok(nm[f"2x2 S={S}"] >= nm[f"1x1 S={S}"] and nm[f"3x3 S={S}"] >= nm[f"2x2 S={S}"], f"{p}: N_max not monotone in the mesh at S={S}")
        ok(nm["3x3 S=1024"] > nm["1x1 S=1024"], f"{p}: 3x3 certifies no larger N than 1x1 at 1,024 slots")
        rows[p] = {k: nm[k] for k in nm if k.split(" S=")[0] in ("1x1", "2x2", "3x3")}
    # recompute two entries from the closed forms (guards the table file)
    for name, N, W, H, r in (("fib", 20, 3, 3, 3), ("treesum_direct", 14, 3, 3, 3)):
        b = eal.bound(progs.book(name, N))
        S = PL.min_slots(W, H, b["B_nodes"], b["B_vars"], r=r)
        ok(S == tab[name]["bench_min_S"]["3x3"] and S <= 65536 and b["slots_1x1"] > 65536,
           f"{name}({N}) 3x3: smallest certified cell {S} (table {tab[name]['bench_min_S']['3x3']}), one cell needs {b['slots_1x1']}")
        ok(not PL.certified(W, H, b["B_nodes"], b["B_vars"], S - 1, r=r), f"{name}({N}): {S - 1} slots must not certify")
    out["table"] = rows
    print("  table: N_max per cell size, 1x1 (step 28) / 2x2 / 3x3:", flush=True)
    for p, nm in rows.items():
        print("    " + p.ljust(15) + "  ".join(f"{S}: " + "/".join(str(nm[f'{m} S={S}']) for m in ('1x1', '2x2', '3x3')) for S in (1024, 4096, 65536)), flush=True)


# ------------------------------------------------------------------------------------------------ RTL
def rtl_case(name, N, W, H, r, S, keep=None, Sb=None, seed=1, claim=True, **kn):
    book = progs.book(name, N)
    b = eal.bound(book)
    Ln, Lv = b["B_nodes"], b["B_vars"]
    Sb = Sb or S
    cs = PL.cells(W, H)
    img, used0 = None, 0
    if keep is not None or Sb != S:
        keep = keep or {c: S for c in cs}
        img = fabric.Image(book, W, H, Sb, 1024)
        for c in cs:
            fnl = [s for s in range(Sb) if img.nodes[c][s] is None]
            fvl = [s for s in range(Sb) if img.vars[c][s] is None]
            for s in fnl[keep[c]:]: img.nodes[c][s] = [mk(ERA), mk(ERA)]; img.nown[c][s] = 14
            for s in fvl[keep[c]:]: img.vars[c][s] = mk(NONE); img.vown[c][s] = 14
        used0 = W * H * Sb - sum(keep.values())
        cert = PL.certify(W, H, Ln, Lv, free_n=keep, free_v=keep, S=S, r=r)
    else:
        cert = PL.certify(W, H, Ln, Lv, S=S, r=r)
    ok(cert == claim, f"{name}({N}) {W}x{H} r{r} S{S}: certificate {cert}, expected {claim}")
    res = rtl.run(book, W, H, slots=Sb, img=img, seed=seed, maxcycles=8_000_000, timeout=3000, extra=[f"+pcert={r}", f"+rgrad={r}"] + kn.pop("extra", []), **kn)
    live = (res.get("pcert_used_n", 0) - used0, res.get("pcert_used_v", 0) - used0)
    good = res["status"] == 0 and res["readback"] == progs.expected(name, N) and res.get("interactions") == b["interactions"]
    if claim:
        ok(good and res.get("pcert_viol") == 0 and live[0] <= Ln and live[1] <= Lv,
           f"RTL {name}({N}) {W}x{H} r{r} S{S}: status {res['status']} {res['readback']} viol {res.get('pcert_viol')} live {live} L ({Ln}, {Lv})")
    return res, live, (Ln, Lv)


def rtl_small(quick):
    tab = json.load(open(TAB))
    meshes = [(2, 2, 3, "2x2"), (3, 3, 3, "3x3"), (3, 3, 4, "3x3 rgrad 4")]
    progs_ = ["fib", "treesum", "sum", "qsort_l"] if quick else ["sum", "list", "higher", "fib", "treesum", "treesum_direct", "sort", "qsort_l"]
    knobs = [dict(seed=1, jitter=30)] if quick else [dict(seed=1, jitter=30), dict(seed=2, stall=20, pmsg=32), dict(seed=3, extra=["+ilr=2"])]
    rows = {}
    for p in progs_:
        n1 = tab[p]["nmax"]["1x1 S=1024"]
        for W, H, r, mn in (meshes[:2] if quick else meshes):
            N = tab[p]["nmax"][f"{mn} S=1024"]
            ok(N > n1 or (mn == "2x2" and N >= n1), f"{p} {mn}: N {N} vs 1x1 {n1}")
            for kn in knobs:
                res, live, L = rtl_case(p, N, W, H, r, 1024, **dict(kn))
                rows[f"{p}({N}) {mn} seed {kn['seed']}"] = {"status": res["status"], "cycles": res.get("cycles"), "live": live, "L": L,
                                                           "pcert_min": res.get("pcert_min")}
        print(f"  RTL {p}: 1x1 certifies N <= {n1} at 1,024 slots; " + ", ".join(f"{mn} N = {tab[p]['nmax'][mn + ' S=1024']}" for _, _, _, mn in (meshes[:2] if quick else meshes))
              + f" run certified ({len(knobs)} knob sets each)", flush=True)
    out["rtl_small"] = rows


def rtl_hetero(quick):
    cs = PL.cells(3, 3)
    corner = {c: 8 for c in cs}; corner[(2, 2)] = 1024
    centre = {c: 8 for c in cs}; centre[(1, 1)] = 1024
    cases = [("fib", 7), ("treesum", 4)] if quick else [("fib", 7), ("treesum", 4), ("sum", 60), ("list", 12)]
    for name, N in cases:
        res4, _, _ = rtl_case(name, N, 3, 3, 4, 1024, keep=corner, claim=True, jitter=30)
        res3, _, _ = rtl_case(name, N, 3, 3, 3, 1024, keep=corner, claim=False, jitter=30)
        ok(res3.get("pcert_viol", 0) > 0, f"corner room at rgrad 3, {name}({N}): the audit must see cells without room in reach (viol {res3.get('pcert_viol')})")
        rtl_case(name, N, 3, 3, 3, 1024, keep=centre, claim=True, seed=2, stall=20)
        print(f"  RTL ballast {name}({N}) 3x3 (8 free slots in 8 cells): room in the corner certified at rgrad 4 "
              f"(status {res4['status']}, audit 0), uncertified at rgrad 3 (audit {res3.get('pcert_viol')} cell-cycles without room in reach, "
              f"status {res3['status']}); room in the centre certified at rgrad 3", flush=True)


def rtl_big(quick):
    rows = {}
    cases = [("treesum_direct", 14)] if quick else [("fib", 20), ("treesum_direct", 14)]
    for name, N in cases:
        b = eal.bound(progs.book(name, N))
        S = PL.min_slots(3, 3, b["B_nodes"], b["B_vars"], r=3)
        for seed, kn in ((1, {}),) if quick else ((1, {}), (2, dict(jitter=30)), (3, dict(stall=30, extra=["+ilr=2"]))):
            t = time.time()
            res, live, L = rtl_case(name, N, 3, 3, 3, S, Sb=65536, seed=seed, **dict(kn))
            pk = max(max(c.get("peak_nodes", 0), c.get("peak_vars", 0)) for c in res["cells"].values()) - (65536 - S)
            rows[f"{name}({N}) seed {seed}"] = {"S": S, "status": res["status"], "cycles": res.get("cycles"), "live": live, "L": L, "cell_peak": pk}
            print(f"  RTL {name}({N}) 3x3 x {S} slots (smallest certified; one cell would need {b['slots_1x1']}): status {res['status']}, "
                  f"{res.get('cycles')} cycles, live peak {live} vs L {L}, largest per-cell peak {pk} ({time.time() - t:.0f}s)", flush=True)
    out["rtl_big"] = rows


# ------------------------------------------------------------------------------------------------ admission
def admission_cmp(quick):
    specs = [("treesum", 6), ("fib", 10), ("sum", 200), ("list", 30), ("qsort_l", 10), ("higher", 30), ("fib", 9), ("treesum", 5)]
    if quick: specs = specs[:5]
    W = H = 3; S = 2048
    mk_jobs = lambda: [admission.Job(f"{n}({N})", progs.source(n, N), k % 14 + 1) for k, (n, N) in enumerate(specs)]
    base = admission.Scheduler(mk_jobs(), W, H, S, admit=True, dedupe=True).run(audit=True)
    pj = mk_jobs()
    sp = admission.Scheduler(pj, W, H, S, admit=True, dedupe=True, placement=True)
    rp = sp.run(audit=True)
    exp = [progs.expected(n, N) for n, N in specs]
    good = lambda r: sum(1 for k, j in enumerate(r["jobs"]) if j["state"] == "done" and j["result"] == exp[k])
    rej_b = sum(1 for j in base["jobs"] if j["state"] == "rejected")
    ok(rp["status"] == "ok" and rp["violation"] is None and good(rp) == len(specs), f"placement admission (model): {rp['status']} {rp['violation']} {good(rp)}/{len(specs)}")
    ok(rp["budget"][0] > base["budget"][0] and rp["budget"][1] > base["budget"][1], f"placement budgets {rp['budget']} vs per-cell {base['budget']}")

    def conc(r):
        ev = sorted((t, 0 if k == "done" else 1) for t, k, _ in r["events"] if k in ("start", "done"))
        c = m = 0
        for _, k in ev:
            c += 1 if k else -1; m = max(m, c)
        return m
    ok(conc(rp) >= conc(base), f"placement admission runs at most as many jobs at once: {conc(rp)} vs {conc(base)}")
    rj = mk_jobs()
    rr = adm_rtl.run_admitted(rj, W, H, S, seed=1, noprog=200000, placement=True)
    p_order = sorted((k for k, j in enumerate(rp["jobs"]) if j["start"] is not None), key=lambda k: (rp["jobs"][k]["start"], k))
    r_order = [e[1] for e in rr["events"] if e[0] == "start"]
    r_ok = sum(1 for k, j in enumerate(rr["jobs"]) if j["state"] == "done" and j["result"] == exp[k])
    ok(rr["status"] == 0 and not rr["blocked"] and r_ok == len(specs) and rr.get("nviol") == 0, f"placement admission (RTL): status {rr['status']} {r_ok}/{len(specs)} viol {rr.get('nviol')}")
    ok(r_order == p_order and rr["interactions"] == rp["interactions"] and tuple(rr["budget"]) == tuple(rp["budget"]),
       f"placement admission: RTL order {r_order} vs model {p_order}, interactions {rr['interactions']} vs {rp['interactions']}, budgets {rr['budget']} {rp['budget']}")
    out["admission"] = {"budget_per_cell": base["budget"], "budget_placement": rp["budget"], "cycles_per_cell": base["cycles"], "cycles_placement": rp["cycles"],
                        "rtl_cycles": rr["cycles"], "max_concurrent": (conc(base), conc(rp)), "rejected_per_cell": rej_b}
    print(f"  admission 3x3 x {S}: per-cell budgets {base['budget']} ({rej_b} rejected, {conc(base)} jobs at once, {base['cycles']} cycles) vs placement "
          f"budgets {rp['budget']} ({conc(rp)} at once, {rp['cycles']} cycles, model audit clean); RTL controller with the same budgets: order = model, "
          f"{rr['interactions']} interactions, {rr['cycles']} cycles", flush=True)


def main(argv):
    t0 = time.time()
    quick = "--quick" in argv
    ci = "--ci" in argv
    if "--mutants" in argv: return mutants()
    print("step 29: placement-aware memory certificate", flush=True)
    checker(600 if ci else 2500)
    load_is_bound()
    table()
    if not ci:
        rtl_small(quick)
        rtl_hetero(quick)
        rtl_big(quick)
        admission_cmp(quick)
    if "--json" in argv:
        with open(argv[argv.index("--json") + 1], "w") as f: json.dump(out, f, indent=1, default=str)
    print(f"step 29 tests: {passed}/{passed + failed} pass ({time.time() - t0:.0f}s)", flush=True)
    return 0 if failed == 0 else 1


MUTANTS = {1: "watermark ignored (a cell counts as poor only when full)", 2: "nodes and vars checked separately",
           3: "rgrad ignored (every cell sees the whole mesh)", 4: "lm_lo >= D_max not required",
           5: "poor-cell cost off by one", 6: "ball one hop too wide", 7: "ballast / other tenants ignored",
           8: "admission budgets one cell too generous"}


def mutants():
    caught = 0
    for m, what in MUTANTS.items():
        env = dict(os.environ, OMEGA_S29_MUT=str(m), PYTHONPATH=f"{ROOT}:{HERE}")
        p = subprocess.run([sys.executable, __file__, "--ci"], env=env, capture_output=True, text=True, timeout=3600)
        c = p.returncode != 0
        caught += c
        first = next((l for l in p.stdout.splitlines() if l.startswith("FAIL")), p.stderr[-300:].replace("\n", " "))
        print(f"  mutant {m} ({what}): {'caught' if c else 'NOT caught'}  [{first[:160]}]", flush=True)
    print(f"s29 mutants: {caught}/{len(MUTANTS)} caught", flush=True)
    return 0 if caught == len(MUTANTS) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
