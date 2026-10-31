"""Memory-pressure tests (SPEC 5, "memory pressure"): a cell that runs out of slots must move work and
nodes to neighbours with free memory instead of retrying in place.

Every cell drives `roomy` (free node and var slots >= SLOTS/4; cleared below SLOTS/8: hysteresis);
`hungry` requires `roomy`; an out-of-memory cell forwards SPAWNs to a roomy neighbour; a rule that lacks
slots moves its node(s) to a roomy neighbour (NODE for SWI, the PULL protocol for a commutation).

Cases
* ballast: cell (0,0) is pre-filled with unreachable nodes / vars of a foreign owner (14), leaving only
  a few free slots, and the program is loaded there.  Without the mechanism the cell livelocks retrying
  rules it has no room for (v3 RTL: 7 of these 30 cases time out); with it all must finish.
* near-overfull (step 22): treesum(9) 3x3 with 500 free slots in the corner, 8 elsewhere; needs the low-memory watermarks.
* expansion order (step 23): treesum(9) on one cell with 130 / 250 free slots: needs +ilr=2 / +ilr=1 on the RTL.
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
# step 22: near-overfull global pressure: 8 cells keep 8/8 free slots, the corner keeps NEAR_K (treesum(9) needs 451-470
# free slots on a 1x1 RTL cell, 115 on the fabric model's).  With the step-21 watermarks (+lm=0) these seeds stop
# (fabric seed 14, RTL seed 9); with the step-22 low-memory watermarks (default +lm=2) they finish.
NEAR = [("treesum", 9, 3, 3)]
NEAR_K, NEAR_FSEEDS, NEAR_RSEEDS = 500, (14,), (9,)
OVERFULL = [("treesum", 9, 2, 2, 24), ("qsort", 30, 2, 2, 24)]
# step 23: one 1x1 cell with K free node = var slots.  treesum(9) needs 120 on the RTL with +ilr=2 (root link deferred
# and the model's child order), 235 with +ilr=1, 451-470 with +ilr=0 (step 22; results/s23/thr.log); the fabric model,
# which always reduces in the +ilr=2 order, needs 115.  (name, N, K, ilr)
ILR_CASES = [("treesum", 9, 130, 2), ("treesum", 9, 250, 1)]


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


def near_img(book, W, H, K):
    from omega.ports import mk, ERA, NONE
    i = ballast_img(book, W, H, 1024, *GKEEP, tuple((x, y) for x in range(W) for y in range(H) if (x, y) != (W - 1, H - 1)))
    c = (W - 1, H - 1)
    fn = [t for t in range(1024) if i.nodes[c][t] is None]; fv = [t for t in range(1024) if i.vars[c][t] is None]
    for t in fn[K:]: i.nodes[c][t] = [mk(ERA), mk(ERA)]; i.nown[c][t] = 14
    for t in fv[K:]: i.vars[c][t] = mk(NONE); i.vown[c][t] = 14
    return i


def run_near(use_rtl=True, mut=0, verbose=True):
    """Step 22: near-overfull global pressure must finish (semantic vs fabric vs RTL)."""
    n = fails = 0; tag = None
    for name, N, W, H in NEAR:
        book = progs.book(name, N); want = progs.expected(name, N); ref = semantic.result(book, fuel=10**8)
        if mut == 0:
            for s in NEAR_FSEEDS:
                n += 1
                try:
                    f = fabric.Fabric(book, W, H, seed=s, p_jitter=0.1, img=near_img(book, W, H, NEAR_K)).run()
                    ok = f.readback() == want and f.interactions == ref["interactions"]
                except Exception as e:
                    ok = False
                if not ok:
                    fails += 1; tag = f"near {name}({N}) {W}x{H} corner {NEAR_K} fabric seed {s}"
                    if verbose: print("FAIL", tag, flush=True)
        if use_rtl:
            from omega import rtl
            for s in NEAR_RSEEDS:
                n += 1
                r = rtl.run(book, W, H, img=near_img(book, W, H, NEAR_K), seed=s, jitter=30, mut=mut, maxcycles=400_000, timeout=900)
                if r["status"] != 0 or r["readback"] != want or r["interactions"] != ref["interactions"]:
                    fails += 1; tag = f"near {name}({N}) {W}x{H} corner {NEAR_K} RTL seed {s}: status {r['status']}"
                    if verbose: print("FAIL", tag, flush=True)
    return n, fails, tag


def run_ilr(use_rtl=True, mut=0, verbose=True):
    """Step 23: an expansion's internal redexes before its root link (+ilr) lowers the one-cell peak."""
    n = fails = 0; tag = None
    for name, N, K, ilr in ILR_CASES:
        book = progs.book(name, N); want = progs.expected(name, N); ref = semantic.result(book, fuel=10**8)
        if mut == 0:
            n += 1
            try:
                f = fabric.Fabric(book, 1, 1, img=ballast_img(book, 1, 1, 1024, K, K)).run()
                ok = f.readback() == want and f.interactions == ref["interactions"]
            except Exception:
                ok = False
            if not ok:
                fails += 1; tag = f"ilr {name}({N}) 1x1 keep {K} fabric"
                if verbose: print("FAIL", tag, flush=True)
        if use_rtl:
            from omega import rtl
            n += 1
            i0 = fabric.ILR; fabric.ILR = ilr
            try:
                r = rtl.run(book, 1, 1, img=ballast_img(book, 1, 1, 1024, K, K), mut=mut, maxcycles=400_000, timeout=600)
            finally:
                fabric.ILR = i0
            if r["status"] != 0 or r["readback"] != want or r["interactions"] != ref["interactions"]:
                fails += 1; tag = f"ilr {name}({N}) 1x1 keep {K} RTL +ilr={ilr}: status {r['status']}"
                if verbose: print("FAIL", tag, flush=True)
    return n, fails, tag


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
    if not quick:
        n2, f2, tag = run_near(use_rtl, mut, verbose)
        n += n2; fails += f2
        if mut and f2: return n, fails, tag
    if not quick:
        n2, f2, tag = run_ilr(use_rtl, mut, verbose)
        n += n2; fails += f2
        if mut and f2: return n, fails, tag
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
