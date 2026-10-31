"""Memory-pressure tests (SPEC 5, "memory pressure"): a cell that runs out of slots must move work and
nodes to neighbours with free memory instead of retrying in place.

Every cell drives `roomy` (free node and var slots >= SLOTS/4; cleared below SLOTS/8: hysteresis);
`hungry` requires `roomy`; an out-of-memory cell forwards SPAWNs to a roomy neighbour; a rule that lacks
slots moves its node(s) to a roomy neighbour (NODE for SWI, the PULL protocol for a commutation).

Cases
* ballast: cell (0,0) is pre-filled with unreachable nodes / vars of a foreign owner (14), leaving only
  a few free slots, and the program is loaded there.  Without the mechanism the cell livelocks retrying
  rules it has no room for (v3 RTL: 7 of these 30 cases time out); with it all must finish.
* keep 0/8 (step 21): no free node slot at all in (0,0); needs the full-cell pass-on (rule d).
* capacity: programs whose one-cell peak exceeds a (small) cell, on 2x2 / 4x4.
* the multi-tenant security fuzz case 265 (one cell needed 1217 vars in a 1024-slot cell on the v2 RTL).
Each case: semantic model (golden) vs fabric model vs RTL: readback, interaction count.

usage: test_mempress.py [--no-rtl] [--mut M] [--quick]
"""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from omega import semantic, fabric, progs
from omega.ports import *

BALLAST = [("fib", 12), ("qsort", 15), ("treesum", 6), ("list", 20), ("sort", 10)]
BSHAPES = [(2, 2), (3, 2)]
BKEEP = [(8, 8), (30, 30), (4, 200), (0, 8)]  # free (node, var) slots left in cell (0,0)
# (0, 8), step 21: zero free node slots in the program's home cell.  The first NODE that reaches (0,0) waits at
# its ejection head; the cell has nothing else to do, so only the full-cell pass-on (rule d, SPEC 5) moves it on
# and unblocks the LINKs queued behind it.  Without rule d (mutant 50) all 10 cases stop (status 3) at the
# default +rsv=1 (results/s21: fabric 150/150 keep-0 runs stuck without the pass-on, 0 with it)
CAPACITY = [("qsort", 24, 256, 2, 2), ("higher", 30, 256, 2, 2), ("sort", 30, 128, 2, 2), ("list", 120, 256, 4, 4),
            ("qsort", 40, 256, 4, 4)]


# global memory pressure (step 10): every cell except the far corner (W-1, H-1) is filled with ballast,
# so the room is several hops from the program (no roomy neighbour on the way: a parked SPAWN must
# fall back to forwarding after its retry-slot timeouts).  OVERFULL: the whole fabric is too small; the
# run must not finish with a wrong answer (status 3 = out of memory / no progress is the accepted end).
GLOBAL = [("fib", 12, 3, 3), ("treesum", 6, 3, 3), ("list", 20, 3, 2), ("qsort", 15, 4, 4), ("sort", 10, 3, 3)]
GKEEP = (8, 8)
# step 19: the near-overfull global case whose livelock at a short retry timeout led to the room-distance
# gradient (kept out of GLOBAL so bench/rto18_rtl.py stays comparable with step 18)
GLOBAL19 = [("treesum", 9, 3, 3)]
OVERFULL = [("treesum", 9, 2, 2, 24), ("qsort", 30, 2, 2, 24)]


def ballast_img(book, W, H, slots, keep_n, keep_v, cells=((0, 0),)):
    img = fabric.Image(book, W, H, slots, 1024)
    for c in cells:
        fn = [s for s in range(slots) if img.nodes[c][s] is None]
        fv = [s for s in range(slots) if img.vars[c][s] is None]
        for s in fn[keep_n:]:
            img.nodes[c][s] = [mk(ERA), mk(ERA)]; img.nown[c][s] = 14
        for s in fv[keep_v:]:
            img.vars[c][s] = mk(NONE); img.vown[c][s] = 14
    return img


def run_overfull(use_rtl=True, mut=0, verbose=True):
    """Globally full fabric: no wrong answer and no silent corruption (status 3 / err accepted)."""
    n = fails = 0
    for name, N, W, H, keep in OVERFULL:
        book = progs.book(name, N)
        want = progs.expected(name, N)
        cells = [(x, y) for x in range(W) for y in range(H)]
        n += 1
        if use_rtl:
            from omega import rtl
            r = rtl.run(book, W, H, img=ballast_img(book, W, H, 1024, keep, keep, cells), seed=5, mut=mut,
                        maxcycles=300_000, timeout=300)
            bad = r["status"] == 0 and r["readback"] != want
            park = sum(c.get("park", 0) for c in r["cells"].values())
            if verbose:
                print(f"overfull {name}({N}) {W}x{H} keep {keep}: status {r['status']} err {r.get('err')} "
                      f"interactions {r['interactions']} msgs {r['msgs']} parks {park}" + ("  WRONG ANSWER" if bad else ""), flush=True)
            fails += bad
    return n, fails


def cases(quick=False):
    out = []
    for name, N in BALLAST:
        for W, H in BSHAPES:
            for kn, kv in BKEEP:
                out.append((f"ballast {name}({N}) {W}x{H} keep {kn}/{kv}", name, N, W, H, 1024, (kn, kv)))
    for name, N, W, H in (GLOBAL[:2] if quick else GLOBAL):
        cells = tuple((x, y) for x in range(W) for y in range(H) if (x, y) != (W - 1, H - 1))
        out.append((f"global {name}({N}) {W}x{H} keep {GKEEP[0]}/{GKEEP[1]} in {len(cells)} cells", name, N, W, H, 1024, GKEEP + (cells,)))
    for name, N, W, H in ([] if quick else GLOBAL19):
        cells = tuple((x, y) for x in range(W) for y in range(H) if (x, y) != (W - 1, H - 1))
        out.append((f"global {name}({N}) {W}x{H} keep {GKEEP[0]}/{GKEEP[1]} in {len(cells)} cells", name, N, W, H, 1024, GKEEP + (cells,)))
    if not quick:
        for name, N, slots, W, H in CAPACITY:
            out.append((f"capacity {name}({N}) slots={slots} {W}x{H}", name, N, W, H, slots, None))
    return out


def run_cases(use_rtl=True, mut=0, verbose=True, quick=False, security=True):
    n = fails = 0
    t0 = time.time()
    for j, (tag, name, N, W, H, slots, keep) in enumerate(cases(quick)):
        book = progs.book(name, N)
        ref = semantic.result(book, fuel=10**8)
        want = progs.expected(name, N)
        mkimg = (lambda: ballast_img(book, W, H, slots, *keep)) if keep else (lambda: fabric.Image(book, W, H, slots, 1024))
        n += 1
        errs = []
        if mut == 0:
            try:
                f = fabric.Fabric(book, W, H, slots=slots, qdepth=1024, seed=j + 1, p_jitter=0.1, img=mkimg()).run()
                if f.readback() != want or f.interactions != ref["interactions"]:
                    errs.append(f"fabric {f.readback()[:40]} / {f.interactions} want {want} / {ref['interactions']}")
            except Exception as e:
                errs.append(f"fabric error {str(e)[:60]}")
        if use_rtl:
            from omega import rtl
            try:
                r = rtl.run(book, W, H, slots=slots, img=mkimg(), seed=j + 3, jitter=30, mut=mut, maxcycles=2_000_000, timeout=300)
                if r["status"] != 0 or r["readback"] != want or r["interactions"] != ref["interactions"]:
                    errs.append(f"rtl status {r['status']} {r['readback'][:40]} / {r['interactions']} want {want} / {ref['interactions']}")
            except Exception as e:
                errs.append(f"rtl error {str(e)[:60]}")
        if errs:
            fails += 1
            if verbose: print(f"FAIL {tag}: " + "; ".join(errs), flush=True)
            if mut: return n, fails, tag
    if use_rtl and not quick and mut == 0:
        n2, f2 = run_overfull(use_rtl, mut, verbose)
        n += n2; fails += f2
    if security and not quick:
        import test_security as ts
        book, tenants, W, H, kn, att = ts.fuzz_case(265)
        n += 1
        ok, _, _ = ts.check("mt-fuzz 265", book, tenants, W, H, use_rtl, mut=mut, verbose=verbose, **kn)
        fails += not ok
    if verbose:
        print(f"memory-pressure tests: {n - fails}/{n} pass [{'semantic + fabric + RTL' if use_rtl else 'semantic + fabric'}] {time.time() - t0:.0f}s")
    return n, fails, None


if __name__ == "__main__":
    mut = int(sys.argv[sys.argv.index("--mut") + 1], 0) if "--mut" in sys.argv else 0
    n, fails, _ = run_cases("--no-rtl" not in sys.argv, mut, quick="--quick" in sys.argv)
    sys.exit(1 if fails else 0)
