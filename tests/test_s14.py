"""Step 14 cross-check: fork deque + oldest-fork give in the fabric model and in the RTL, against the
semantic reducer (readback, interaction count, live node count), for every fork-deque mode (+s14 0/1/2),
with the governor relax knob on and off; the give must actually happen in both models on fork programs
(mode 2 never on qsort, whose fork is stream-fed), and mode 0 must give nothing."""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from omega import progs, semantic, fabric, rtl

CASES = [("fib", 11), ("treesum", 6), ("treesum_direct", 8), ("qsort", 12), ("list", 15), ("higher", 8)]


def main():
    n = fails = 0; t = time.time()
    for name, N in CASES:
        b = progs.book(name, N); ref = semantic.result(b); exp = progs.expected(name, N)
        fork = name in ("fib", "treesum", "treesum_direct")
        for (W, H) in ((2, 2), (4, 4), (3, 2)):
            for mode in (0, 1, 2):
                for nb in ((0, 2), (5, 1)) if mode else ((0, 2),):
                    seed = 7 * W + mode + nb[0]
                    f = fabric.Fabric(b, W, H, seed=seed, s14=mode, gov_nb=nb[0], gov_l0=nb[1], p_jitter=0.05).run()
                    r = rtl.run(b, W, H, seed=seed, jitter=20, s14=mode, govnb=nb[0], govl0=nb[1])
                    fg = sum(c.st.get("botgive", 0) for c in f.cells.values())
                    want_give = fork and mode != 0 and W * H >= 4
                    ok = (f.readback() == exp and f.interactions == ref["interactions"] and r["status"] == 0
                          and r["readback"] == ref["readback"] and r["interactions"] == ref["interactions"]
                          and r["node_count"] == ref["nodes"]
                          and (fg > 0) == want_give and (r["fgive"] > 0) == want_give)
                    n += 1
                    if not ok:
                        fails += 1
                        print(f"FAIL {name}({N}) {W}x{H} s14={mode} gov_nb={nb}: rtl {r['readback'][:40]} {r['interactions']}/{ref['interactions']} "
                              f"fgive {r['fgive']}, fabric {f.readback()[:40]} give {fg}", flush=True)
    print(f"step 14 cross-check: {n - fails}/{n} pass ({time.time() - t:.0f}s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
