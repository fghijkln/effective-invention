"""Step 30 tests: joint node + var loads, the task-stack bound and the certificate built on them (omega/joint.py,
SPEC §7.9).

* hull: for tiny suite programs and random event DAGs, every causally closed set is enumerated (brute force,
  `joint.downsets`, independent of the min cut): Phi(lam) = max over closed sets of lam*n + v for every grid lam,
  W_nodes = max n, B_vars = max v, Q = max(n + 2v) + A + 1; the fixpoint attainer is closed and inside the hull;
* semantic property: under random schedules, every step, pending redexes <= n + 2v + A and (n, v) inside the hull;
* checker: `joint.certify_mesh` against the brute-force `joint.witness` (an achievable (n, v) point that makes a whole
  rgrad-ball poor) on random meshes / radii / loads, incl. boundary loads at multiples of m: certified => no witness
  (soundness, required), and how often the converse holds (exactness, reported);
* stack: `certified` refuses QDEPTH < Q + margin + 3; the engine margin is applied;
* closed forms: the fitted W_nodes / B_vars / A / Q forms reproduce the direct (non-extrapolated) values at the
  benchmark sizes (results/s30/direct.json), and the table: every benchmark's smallest certified cell <= step 29's;
  treesum_direct(14) certified on 2x2 at <= 65,536 slots;
* (not --ci) RTL: certified runs sound (+pcert, +tcert, live <= loads, hull, tasks <= Q), uncertified QDEPTH below
  the depth-first need ends in status 2, a fragmented mesh (no roomy cell) stalls, and without +tcert nothing changes.

usage: test_s30.py [--ci] [--mutants]
"""
import sys, os, time, json, random, subprocess
from fractions import Fraction as F
sys.setrecursionlimit(100000)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from omega import joint, progs, fabric, semantic, placement as PL, rtl
from omega.ports import *

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
passed = failed = 0


def ok(cond, msg):
    global passed, failed
    if cond: passed += 1
    else:
        failed += 1; print("FAIL", msg, flush=True)
    return cond


TINY = [("fib", 1), ("fib", 2), ("fib", 3), ("sum", 1), ("sum", 2), ("sum", 3), ("fact", 2), ("list", 1), ("list", 2),
        ("treesum", 1), ("treesum_direct", 1), ("treesum_direct", 2), ("higher", 1), ("sort", 1), ("sort", 2)]


def check_hull(tag, D, L):
    try:
        pts = joint.downsets(D)
    except (OverflowError, RecursionError):
        return False
    ok(max(n for n, v in pts) == L["W_nodes"], f"{tag}: W_nodes {L['W_nodes']} != brute {max(n for n, v in pts)}")
    ok(max(v for n, v in pts) == L["B_vars"], f"{tag}: B_vars {L['B_vars']} != brute {max(v for n, v in pts)}")
    for lam, p in L["hull"]:
        ok(max(lam * n + v for n, v in pts) == p, f"{tag}: Phi({lam}) {p} != brute {max(lam * n + v for n, v in pts)}")
    ok(L["Q"] == max(n + 2 * v for n, v in pts) + D["atoms"] + 1, f"{tag}: Q {L['Q']} != brute {max(n + 2 * v for n, v in pts) + D['atoms'] + 1}")
    return True


def hull():
    done = 0
    for name, N in TINY:
        L = joint.loads(progs.book(name, N))
        if check_hull(f"{name}({N})", L["dag"], L): done += 1
        n, v = joint.attainer(L["dag"])
        ok(n <= L["W_nodes"] and v <= L["B_vars"] and all(lam * n + v <= p for lam, p in L["hull"]), f"{name}({N}): attainer outside hull")
    ok(done >= 8, f"only {done} tiny programs enumerable")
    rnd = random.Random(30)
    for i in range(150):                                         # random DAGs
        n = rnd.randint(4, 14)
        deps = [set()] + [set(rnd.sample(range(e), rnd.randint(0, min(e, 3)))) | {0} for e in range(1, n)]
        D = {"n0": rnd.randint(0, 5), "v0": rnd.randint(0, 3), "w": [0] + [rnd.randint(-3, 4) for _ in range(n - 1)],
             "a": [0] + [rnd.choice((0, 0, 1, 2, 4)) for _ in range(n - 1)], "deps": deps, "atoms": rnd.randint(0, 5)}
        Wn = joint.phi(D, None)
        L = {"W_nodes": Wn, "B_vars": D["v0"] + sum(D["a"][1:]), "hull": [(lam, joint.phi(D, lam)) for lam in joint.LAMS],
             "Q": int(joint.phi(D, 1, 2)) + D["atoms"] + 1}
        if joint.MUT == 1: L["hull"] = [(lam, p - 1 - lam * Wn // 4) for lam, p in L["hull"]]
        if joint.MUT == 2: L["Q"] -= D["atoms"]
        check_hull(f"random dag {i}", D, L)
    print(f"  hull: {done} suite programs + 150 random DAGs enumerated", flush=True)


def semantic_prop():
    viol = steps = 0
    for name, N in (("fib", 5), ("treesum", 3), ("list", 6), ("sum", 10), ("higher", 4), ("treesum_direct", 4), ("sort", 4)):
        bk = progs.book(name, N)
        L = joint.loads(bk)
        for seed in range(6):
            net = semantic.Net(bk)
            root = net.alloc_var()
            net.instantiate(bk.id("main"), mk(VAR, 0, root))
            rng = random.Random(seed)
            while net.rdx:
                i = rng.randrange(len(net.rdx)); net.rdx[i], net.rdx[-1] = net.rdx[-1], net.rdx[i]
                a, b = net.rdx.pop(); net.interact(a, b); steps += 1
                n, v, t = len(net.nodes), len(net.vars), len(net.rdx)
                if t > n + 2 * v + L["atoms"] or n > L["W_nodes"] or v > L["B_vars"] or any(lam * n + v > p for lam, p in L["hull"]):
                    viol += 1
    ok(viol == 0, f"semantic schedules: {viol} steps outside the loads / task bound")
    print(f"  semantic: {steps} steps, {viol} outside", flush=True)


def checker(n=1500):
    rnd = random.Random(3011)
    unsound = exact = total = 0
    for i in range(n):
        W, H = rnd.choice([(2, 1), (2, 2), (3, 2), (2, 3), (3, 3), (4, 2)])
        r = rnd.randint(1, 4)
        S = rnd.choice([80, 100, 256])
        m = S - fabric.LM_HI + 1
        k = rnd.randint(1, 6)
        if rnd.random() < 0.4:                                   # boundary points at multiples of m
            pts = {(rnd.randint(0, k) * m + rnd.choice((-1, 0, 0, 1)), rnd.randint(0, k) * m + rnd.choice((-1, 0, 0, 1))) for _ in range(rnd.randint(1, 3))}
        else:
            pts = {(rnd.randint(0, k * m), rnd.randint(0, k * m)) for _ in range(rnd.randint(1, 6))}
        pts = {(max(0, a), max(0, b)) for a, b in pts}
        L = {"W_nodes": max(a for a, b in pts), "B_vars": max(b for a, b in pts),
             "hull": [(lam, max(lam * a + b for a, b in pts)) for lam in joint.LAMS]}
        c = joint.certify_mesh(W, H, L, S=S, r=r)
        w = joint.witness(W, H, pts, S, r=r)
        total += 1
        if c and w is not None:
            unsound += 1
            if unsound <= 3: print(f"  unsound {W}x{H} r{r} S{S} pts {sorted(pts)}: witness {w}", flush=True)
        if c == (w is None): exact += 1
    ok(unsound == 0, f"checker: {unsound} certified configurations have a witness")
    print(f"  checker: {total} cases, 0 unsound required ({unsound}), exact {exact}/{total}", flush=True)
    return exact, total


def stack_and_margin():
    L = joint.loads(progs.book("fib", 8))
    for W, H in ((1, 1), (2, 2), (3, 3)):
        q = joint.qdepth_needed(W, H, L)
        ok(q == L["Q"] + joint.ENG * W * H + 3, f"qdepth_needed {W}x{H}: {q}")
        ok(joint.certified(W, H, L, 1 << 16, q) and not joint.certified(W, H, L, 1 << 16, q - 1), f"stack check {W}x{H}")
    # the engine margin: a mesh certified at S must also hold with the margin made explicit by hand
    for W, H, r in ((2, 2, 3), (3, 3, 3), (4, 4, 6)):
        S = joint.min_slots(W, H, L, r=r)
        Lm = dict(L, W_nodes=L["W_nodes"] + 2 * W * H, hull=[(lam, p + lam * 2 * W * H) for lam, p in L["hull"]])
        pts_ok = joint.certify_mesh(W, H, Lm, S=S, r=r)
        ok(pts_ok, f"{W}x{H}: min S {S} fails with the explicit engine margin")


def forms_and_table():
    tab = json.load(open(os.path.join(ROOT, "results", "s30", "cert_table.json")))
    direct = json.load(open(os.path.join(ROOT, "results", "s30", "direct.json")))
    for key, d in direct.items():
        p = key.split("(")[0]
        bl = tab[p]["bench_L"]
        ok(tuple(bl) == (d["W_nodes"], d["B_vars"]) and tab[p]["bench_Q"] == d["Q"], f"{key}: fitted {bl} Q {tab[p]['bench_Q']} != direct {d['W_nodes']}, {d['B_vars']}, Q {d['Q']}")
    for p, row in tab.items():
        for mname, s in row["bench_min_S"].items():
            ok(s is not None and s <= row["s29_min_S"][mname], f"{p} {mname}: {s} > step 29 {row['s29_min_S'][mname]}")
    ok(tab["treesum_direct"]["bench_min_S"]["2x2"] <= 65536, "treesum_direct(14) not certified on 2x2 x 65,536")
    # pinned: the smallest certified cells, recomputed from the direct loads (mutants that move them are caught)
    pin = {"treesum_direct(14)": {"2x2": 53315, "3x3": 29554}, "fib(20)": {"2x2": 77487, "3x3": 41656}}
    for key, want in pin.items():
        d = direct[key]
        L = {"W_nodes": d["W_nodes"], "B_vars": d["B_vars"], "hull": [(F(l), F(p)) for l, p in d["hull"]], "Q": d["Q"]}
        for mname, s in want.items():
            W = int(mname[0])
            got = joint.min_slots(W, W, L, r=3)
            ok(got == s, f"{key} {mname}: min S {got} != {s}")
    print(f"  table: treesum_direct(14) 2x2 {tab['treesum_direct']['bench_min_S']['2x2']}, fib(20) 2x2 {tab['fib']['bench_min_S']['2x2']}", flush=True)


def rtl_cases():
    sys.path.insert(0, os.path.join(ROOT, "results", "s30"))
    import validate as V
    recs = []
    for key, kw in (("fib 2x2", dict(name="fib", N=9, W=2, H=2, r=3, S=1024, knob=dict(seed=1), qdepth=65536)),
                    ("list 3x3", dict(name="list", N=40, W=3, H=3, r=3, S=1024, knob=dict(seed=2, jitter=30), qdepth=65536)),
                    ("treesum 3x3", dict(name="treesum", N=6, W=3, H=3, r=3, S=1024, knob=dict(seed=3, stall=30), qdepth=65536))):
        rec = V.one(key, **kw); recs.append(rec)
        ok(rec["cert"] and rec["sound"], f"RTL {key}: {rec}")
    rec = V.one("stack q16", name="fib", N=12, W=1, H=1, r=None, S=16384, knob=dict(seed=1), qdepth=16)
    ok(not rec["cert"] and rec["status"] == 2, f"RTL stack q16: {rec['status']}")
    cs = PL.cells(3, 3)
    rec = V.one("frag10", name="treesum", N=4, W=3, H=3, r=3, S=1024, knob=dict(seed=1), qdepth=65536, keep={c: 10 for c in cs}, maxcycles=1_000_000)
    ok(not rec["cert"] and rec["status"] == 3 and rec["pcert_viol"] > 0, f"RTL frag10: {rec['status']}")
    bk = progs.book("fib", 9)
    a = rtl.run(bk, 2, 2, qdepth=65536); b = rtl.run(bk, 2, 2, qdepth=65536, extra=["+tcert=100"])
    ok(a["cycles"] == b["cycles"] and "tcert_viol" not in a and b.get("tcert_viol") == 0, "audit changes the run or prints without +tcert")


def main(argv):
    t0 = time.time()
    ci = "--ci" in argv
    if "--mutants" in argv: return mutants()
    print("step 30: joint loads, task stack, certificate", flush=True)
    hull()
    semantic_prop()
    checker(600 if ci else 1500)
    stack_and_margin()
    forms_and_table()
    if not ci: rtl_cases()
    print(f"step 30 tests: {passed}/{passed + failed} pass ({time.time() - t0:.0f}s)", flush=True)
    return 0 if failed == 0 else 1


MUTANTS = {1: "hull cut below what a closed set attains", 2: "atom pairs left out of the stack bound",
           3: "vars counted once in the stack bound", 4: "off by one at the load cap", 5: "a cell poor only if nodes AND vars short",
           6: "ball one hop too wide", 7: "stack not checked", 8: "no engine margin"}


def mutants():
    caught = 0
    for m, what in MUTANTS.items():
        env = dict(os.environ, OMEGA_S30_MUT=str(m), PYTHONPATH=f"{ROOT}:{HERE}")
        p = subprocess.run([sys.executable, __file__, "--ci"], env=env, capture_output=True, text=True, timeout=3600)
        c = p.returncode != 0
        caught += c
        first = next((l for l in p.stdout.splitlines() if l.startswith("FAIL")), p.stderr[-300:].replace("\n", " "))
        print(f"  mutant {m} ({what}): {'caught' if c else 'NOT caught'}  [{first[:160]}]", flush=True)
    print(f"s30 mutants: {caught}/{len(MUTANTS)} caught", flush=True)
    return 0 if caught == len(MUTANTS) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
