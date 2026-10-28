"""Program tests: every Omega-lang program on the semantic reducer, the fabric model and the RTL
(1x1, 2x2, 4x4, random schedules), plus a performance bound (parallel tree-sum must scale).
usage: test_programs.py [--fuzz K]   (K extra random (program, N, mesh, knobs) cases)"""
import sys, os, random, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from omega import progs, semantic, fabric, rtl

SUITE = [("fib", 12), ("sum", 100), ("fact", 12), ("list", 25), ("treesum", 7), ("treesum_direct", 9),
         ("sort", 15), ("qsort", 15), ("higher", 9)]
SHAPES = [(1, 1), (2, 2), (4, 4)]


def run_case(name, n, W, H, seed, jitter, stall, pmsg, scatter):
    b = progs.book(name, n)
    ref = semantic.result(b)
    exp = progs.expected(name, n)
    img = fabric.Image(b, W, H, 1024, 1024, scatter=scatter)
    r = rtl.run(b, W, H, img=img, seed=seed, jitter=jitter, stall=stall, pmsg=pmsg)
    ok = ref["readback"] == exp and r["readback"] == exp and r["interactions"] == ref["interactions"] and r["node_count"] == ref["nodes"]
    return ok, r, ref


def main():
    fuzz = int(sys.argv[sys.argv.index("--fuzz") + 1]) if "--fuzz" in sys.argv else 0
    n = fails = 0
    t = time.time()
    for name, N in SUITE:
        b = progs.book(name, N)
        ref = semantic.result(b)
        f = fabric.Fabric(b, 2, 2, seed=5, p_jitter=0.1).run()
        if f.readback() != progs.expected(name, N) or f.interactions != ref["interactions"]:
            print(f"FAIL fabric {name}({N})"); fails += 1
        n += 1
        for W, H in SHAPES:
            for k in range(2):
                ok, r, ref = run_case(name, N, W, H, seed=k * 31 + W, jitter=[0, 60][k], stall=[0, 30][k],
                                      pmsg=[128, 40][k], scatter=None)
                n += 1
                if not ok:
                    fails += 1; print(f"FAIL rtl {name}({N}) {W}x{H} k={k}: {r['readback']} {r['interactions']}/{ref['interactions']}")
    # performance bound
    b = progs.book("treesum_direct", 9)
    c1 = rtl.run(b, 1, 1)["cycles"]; c4 = rtl.run(b, 4, 4)["cycles"]
    n += 1
    if c1 / c4 < 3.0:
        fails += 1; print(f"FAIL perf bound: treesum_direct(9) speedup {c1/c4:.2f} < 3")
    rng = random.Random(2026)
    for i in range(fuzz):
        name = rng.choice([s[0] for s in SUITE])
        N = {"fib": rng.randint(0, 11), "sum": rng.randint(0, 120), "fact": rng.randint(0, 13), "list": rng.randint(0, 25),
             "treesum": rng.randint(0, 7), "treesum_direct": rng.randint(0, 9), "sort": rng.randint(0, 14),
             "qsort": rng.randint(0, 14), "higher": rng.randint(0, 20)}[name]
        W, H = rng.choice([(1, 1), (2, 2), (4, 4), (3, 2), (1, 4)])
        ok, r, ref = run_case(name, N, W, H, seed=rng.randint(1, 10**9), jitter=rng.choice([0, 40, 120, 200]),
                              stall=rng.choice([0, 30, 90]), pmsg=rng.randint(0, 255),
                              scatter=rng.randint(0, 10**6) if rng.random() < 0.5 else None)
        n += 1
        if not ok:
            fails += 1; print(f"FAIL fuzz {name}({N}) {W}x{H}: {r['readback']} {r['interactions']}/{ref['interactions']}")
    print(f"program tests: {n - fails}/{n} pass ({time.time() - t:.0f}s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
