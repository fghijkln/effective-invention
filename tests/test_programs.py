"""Program tests: every Omega-lang program on the semantic reducer, the fabric model and the RTL
(1x1, 2x2, 4x4, random schedules), plus a performance bound (parallel tree-sum must scale).
usage: test_programs.py [--fuzz K]   (K extra random (program, N, mesh, knobs) cases)"""
import sys, os, random, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from omega import progs, semantic, fabric, rtl

SUITE = [("fib", 12), ("sum", 100), ("fact", 12), ("list", 25), ("treesum", 7), ("treesum_direct", 9),
         ("sort", 15), ("qsort", 15), ("higher", 9)]
SHAPES = [(1, 1), (2, 2), (4, 4)]


def run_case(name, n, W, H, seed, jitter, stall, pmsg, scatter, spawn=None, link_local=None, s14=None):
    b = progs.book(name, n)
    ref = semantic.result(b)
    exp = progs.expected(name, n)
    img = fabric.Image(b, W, H, 1024, 1024, scatter=scatter)
    r = rtl.run(b, W, H, img=img, seed=seed, jitter=jitter, stall=stall, pmsg=pmsg, spawn=spawn, link_local=link_local, s14=s14)
    ok = ref["readback"] == exp and r["readback"] == exp and r["interactions"] == ref["interactions"] and r["node_count"] == ref["nodes"]
    return ok, r, ref


def main():
    fuzz = int(sys.argv[sys.argv.index("--fuzz") + 1]) if "--fuzz" in sys.argv else 0
    n = fails = 0
    t = time.time()
    # small-N edge cases on the semantic model (N = 0 exercises value arms reaching the root)
    for name, _ in SUITE:
        for N in range(6):
            n += 1
            if semantic.result(progs.book(name, N))["readback"] != progs.expected(name, N):
                fails += 1; print(f"FAIL semantic {name}({N})")
    # step 11 fork hint (loader analysis): exactly the divide-and-conquer recursions are fork targets
    FORK = {"fib": {"fib", "fib__a1"}, "treesum": {"gen", "gen__a2", "tsum", "tsum__a3"}, "qsort": {"qs", "qs__a5"}, "treesum_direct": {"tsum", "tsum__a1"},
            "sum": set(), "fact": set(), "list": set(), "sort": set(), "higher": set()}
    for name, want in FORK.items():
        b = progs.book(name, 3)
        got = {b.defs[i].name for i in fabric.fork_defs(b)}
        n += 1
        if got != want:
            fails += 1; print(f"FAIL fork hint {name}: {sorted(got)} want {sorted(want)}")
    # step 13 producer hint: linear recursions that emit a data structure (call a constructor / an arm of
    # another definition) are producers; strict recursions into an operator are not
    PROD = {"qsort": {"rnd", "rnd__a1", "lo", "lo__a2", "lo__a2__a7", "lo__a2__a8", "hi", "hi__a3", "hi__a3__a9", "hi__a3__a10", "app", "app__a4"},
            "list": {"range", "range__a1", "map", "map__a2"}, "sort": {"rnd", "rnd__a1", "insert", "insert__a3", "insert__a3__a6", "sort", "sort__a4"},
            "higher": {"range", "range__a1"}, "fib": set(), "sum": set(), "fact": set(), "treesum": set(), "treesum_direct": set()}
    for name, want in PROD.items():
        b = progs.book(name, 3)
        got = {b.defs[i].name for i in fabric.fork_defs(b, with_prod=True)[2]}
        n += 1
        if got != want:
            fails += 1; print(f"FAIL producer hint {name}: {sorted(got)} want {sorted(want)}")
    for name, N in SUITE:
        b = progs.book(name, N)
        ref = semantic.result(b)
        f = fabric.Fabric(b, 2, 2, seed=5, p_jitter=0.1).run()
        if f.readback() != progs.expected(name, N) or f.interactions != ref["interactions"]:
            print(f"FAIL fabric {name}({N})"); fails += 1
        n += 1
        for W, H in SHAPES:
            for k in range(3 if W > 1 else 2):
                # schedule 0: default spawn policy and link orientation; schedule 1: the step-10 policy
                # (every REF to a hungry neighbour, A = first var), so both decision paths stay covered;
                # schedule 2 (meshes): step 13 with the governor off (fixed producer threshold spawn_kp = 4)
                ok, r, ref = run_case(name, N, W, H, seed=k * 31 + W, jitter=[0, 60, 30][k], stall=[0, 30, 10][k],
                                      pmsg=[128, 40, 200][k], scatter=None, spawn=[None, (-1, 0), (16, 1, 4, 4, 0)][k], link_local=[None, 0, 1][k])
                n += 1
                if not ok:
                    fails += 1; print(f"FAIL rtl {name}({N}) {W}x{H} k={k}: {r['readback']} {r['interactions']}/{ref['interactions']}")
    # performance bound
    b = progs.book("treesum_direct", 9)
    c1 = rtl.run(b, 1, 1)["cycles"]; c4 = rtl.run(b, 4, 4)["cycles"]
    n += 1
    if c1 / c4 < 3.0:
        fails += 1; print(f"FAIL perf bound: treesum_direct(9) speedup {c1/c4:.2f} < 3")
    # step 11 message bound: low-parallel programs keep their messages per interaction low on 4x4 (the
    # step-10 policy sends about 1.5-1.7 per interaction on these), and stay at least as fast as 1x1
    for name, N, bound in (("qsort", 20, 0.6), ("list", 40, 0.6)):
        b = progs.book(name, N)
        r1 = rtl.run(b, 1, 1, slots=4096); r4 = rtl.run(b, 4, 4)
        mpi = sum(r4["msgs"].values()) / r4["interactions"]
        n += 1
        if mpi > bound or r4["cycles"] > r1["cycles"]:
            fails += 1; print(f"FAIL message bound: {name}({N}) 4x4 {mpi:.2f} msgs/interaction (bound {bound}), cycles {r4['cycles']} vs 1x1 {r1['cycles']}")
    rng = random.Random(2026)
    sprng = random.Random(11)
    sprng13 = random.Random(13)       # step 13 knobs: own stream (the earlier case sequence is unchanged)
    sprng14 = random.Random(14)       # step 14 fork deque on / off (+s14), own stream
    for i in range(fuzz):
        name = rng.choice([s[0] for s in SUITE])
        N = {"fib": rng.randint(0, 11), "sum": rng.randint(0, 120), "fact": rng.randint(0, 13), "list": rng.randint(0, 25),
             "treesum": rng.randint(0, 7), "treesum_direct": rng.randint(0, 9), "sort": rng.randint(0, 14),
             "qsort": rng.randint(0, 14), "higher": rng.randint(0, 20)}[name]
        W, H = rng.choice([(1, 1), (2, 2), (4, 4), (3, 2), (1, 4)])
        ok, r, ref = run_case(name, N, W, H, seed=rng.randint(1, 10**9), jitter=rng.choice([0, 40, 120, 200]),
                              stall=rng.choice([0, 30, 90]), pmsg=rng.randint(0, 255),
                              scatter=rng.randint(0, 10**6) if rng.random() < 0.5 else None,
                              spawn=(sprng.choice([-1, 0, 2, 8, 8, 32]), sprng.choice([0, 1, 1]), fabric.SPAWN_K2,
                                     sprng13.choice([-1, 0, 2, 4, 4, 16]), sprng13.choice([0, 0, 20, 50, 200])),
                              link_local=sprng.choice([0, 1, 1]), s14=sprng14.choice([0, 1, 1]))
        n += 1
        if not ok:
            fails += 1; print(f"FAIL fuzz {name}({N}) {W}x{H}: {r['readback']} {r['interactions']}/{ref['interactions']}")
    print(f"program tests: {n - fails}/{n} pass ({time.time() - t:.0f}s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
