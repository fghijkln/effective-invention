"""Mutation testing of the RTL rewrite engine (rule 'ROM' / rule logic, protocol, quiescence).
Each mutant flips one MUT bit in rtl/omega_cell.sv; the suite must detect it.
usage: mutants.py [bit ...]"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from omega import ir, semantic, fabric, rtl, progs, randnet, lang
import test_units

MUTANTS = {
    0: "erase/copy rule: aux2 receives aux1 instead of the atom",
    1: "OPR: operand order ignores the flip bit",
    2: "OPR: flip bit not toggled when the operator is turned around",
    3: "SWI: predecessor not decremented",
    4: "annihilation ignores DUP labels (commute rule never fires for different labels)",
    5: "annihilation cross-wires aux1 with aux2",
    6: "commutation: second copy of P has its aux ports swapped",
    7: "SPAWN always expands locally (performance-only: no work distribution)",
    8: "ALU: '<' computed as '<='",
    9: "SWI #0: built (* r) instead of (r *) (wrong branch)",
    10: "NODE migration: aux ports swapped when re-homed",
    11: "var exchange: substitution chain not followed (link dropped)",
    12: "eraser only reaches aux1",
    13: "REF ~ DUP expands instead of copying the reference",
    14: "commutation: two fresh wires share one var",
    15: "quiescence detection ignores in-flight router flits",
    16: "security: var slot owner-tag check disabled (forged VAR pointers accepted)",
    17: "security: cross-owner (T1) check disabled",
    18: "security: out-of-bounds pointer check disabled",
    19: "security: expansion does not stamp the tenant's owner (ROM owner 0 leaks into tenants)",
    20: "security: forged-var trap is recorded but the access is not blocked",
    21: "security: node slot owner-tag check disabled",
    22: "v3 read-ahead: write bypass on node read port 1 disabled (stale node data)",
    23: "v4 S_WQ: second queued node write dropped (a commutation copy never written)",
    24: "v3 S_WQ: owner tags of fresh commutation vars not written",
    25: "v3 EXPAND allocation pops one node slot fewer than it maps (slot aliasing)",
    26: "v4 EXPAND: template word entry select wrong (entry i reads entry i xor 1)",
    27: "memory pressure: roomy neighbours ignored (no PULL / NODE offload); run with bit 41 (no escalation) because since step 10 escalation alone also rescues every pressure case (alone: survives)",
    28: "memory pressure: hungry does not require roomy (a full cell still asks for work); since step 19 the full-cell pass-on tolerates it on the quick pressure set, so it runs on the full set and is caught by the step-19 global treesum(9) 3x3 case",
    29: "cluster ROM: arbiter grants more requesters than it has read ports (they get another cell's data)",
    30: "cluster ROM: EXPAND does not wait for its template pair (proceeds on a missed grant)",
    31: "cluster ROM: buffered template word not dropped when a new expansion starts (stale definition)",
    32: "v4 read-ahead: write bypass ignores the second node write port (stale node data)",
    33: "v4 EXPAND: second entry's var tag written to the first entry's var slot",
    34: "v4 EXPAND: advances by two entries when only one was written (entry skipped)",
    35: "VHU: no stall when the main engine's link names the same var slot (non-atomic exchange)",
    36: "VHU: hand-back link never taken by the main engine (redex lost / hang)",
    37: "VHU disabled (performance only: main engine follows every chain; caught by the cycle bound)",
    38: "VHU read-ahead: no bypass of the main engine's var write port 1 (stale var data)",
    39: "retry slot: a parked retry is never taken again (lost work / hang)",
    40: "retry slot: quiescence ignores a parked retry (premature termination)",
    41: "retry slot: no escalation (a parked retry never falls back to round-robin SPAWN / NODE / PULL moves)",
    42: "spawn policy: threshold ignored (every REF to a hungry neighbour, the step-10 policy; performance only: caught by the message bound)",
    43: "spawn policy: fork hint ignored (divide-and-conquer REFs held back by the threshold; performance only: caught by the speed-up bound)",
    44: "local-first link orientation disabled (a remote var ~ local var link is always sent away; performance only: caught by the LINK bound)",
    45: "step 13 producer hint ignored (producer recursions held back by spawn_k like strict ones; performance only: caught by the qsort speed bound)",
    46: "step 13 governor never tightens (the level only relaxes; performance only: caught by the message bound with the governor on)",
    47: "step 14 oldest-fork give disabled (fork tasks leave the deque only when the stack is empty; performance only: caught by the fib(16) 4x4 cycle bound)",
    48: "step 14 fork deque: a fork task that finds the deque full is dropped (lost work)",
    49: "step 19 room-distance gradient ignored (no downhill neighbour is ever found: a SPAWN without room parks and escalates round robin as in step 18; caught by the global treesum(9) 3x3 livelock seeds at the short timeout)",
    52: "step 22 low-memory watermarks never engage (roomy stays SLOTS/4, reserve stays rsv; caught by the near-overfull treesum(9) 3x3 case, corner 500 free slots, RTL seed 9, which stops with status 3)",
    51: "step 20 slot reserve applied without a downhill neighbour (an expansion always leaves rsv slots free while rgrad != 0; caught by fib(10) on 1x1 with exactly the 93 free node / var slots its RTL run needs)",
    50: "step 19 full-cell pass-on off (a NODE / PULL at the ejection head of a cell with no free node slot blocks it again; caught since step 21 at the default +rsv=1 by mempress ballast keep 0/8, a home cell with no free node slot: fib(12) 2x2, treesum(6) 3x2 stop with status 3; step 19's global treesum(7) 8x8 seeds 16 / 18 only stop at +rsv=4)",
}
BOUND47 = 1.05
PROGS = [("fib", 8), ("list", 6), ("sort", 6), ("higher", 5), ("fact", 5), ("treesum", 4), ("qsort", 5), ("sum", 20)]


def same(r, ref):
    return r["status"] == 0 and (r["readback"], r["interactions"], r["node_count"]) == (ref["readback"], ref["interactions"], ref["nodes"])


def try_security(mut):
    import test_security as ts
    cases = [(n, b, t, w, None) for n, b, t, w in ts.demo_cases()] + ts.attack_cases() + ts.cross_cases()
    for j, (name, b, t, want, reasons) in enumerate(cases):
        for (W, H) in ((2, 2), (1, 1)):
            for fi in (0, 1):
                try:
                    ok, ref, r = ts.check(name, b, t, W, H, True, seed=j + 1, jitter=30 * fi, scatter=(j if fi and W > 1 and "result node" not in name else None),
                                          fi=fi, mut=mut, want=want, honest=([0] if reasons else None), verbose=False)
                except Exception as e:
                    return True, f"{name} {W}x{H}: simulator error {str(e)[:80]}"
                if not ok:
                    return True, f"{name} on {W}x{H} fi={fi}: honest result / trap set differs (rtl traps {r and r['traps']}, semantic {ref['traps']})"
    return False, f"survived {len(cases)} security cases"


def try_mutant(bit):
    mut = 1 << bit
    if 16 <= bit <= 21:
        return try_security(mut)
    if bit == 27:
        mut |= 1 << 41      # escalation masks the missing roomy offload (it is a fast path since step 10)
    if bit in (27, 28, 39, 40, 41):
        import test_mempress
        n, fails, tag = test_mempress.run_cases(True, mut, verbose=False, quick=bit == 27)
        return bool(fails), (f"{tag}: wrong result / timeout" if fails else f"survived {n} memory-pressure cases")
    if bit == 37:
        b = progs.book("fib", 12)
        c0 = rtl.run(b, 1, 1)["cycles"]
        c1 = rtl.run(b, 1, 1, mut=mut)["cycles"]
        return (c1 > 1.1 * c0), f"fib(12) 1x1 cycles {c1} with the mutant vs {c0} (bound: > 1.1x)"
    if bit == 42:
        b = progs.book("qsort", 20)
        r = rtl.run(b, 4, 4, mut=mut)
        mpi = sum(r["msgs"].values()) / r["interactions"]
        return (mpi > 0.6), f"qsort(20) 4x4 {mpi:.2f} msgs/interaction with the mutant (bound <= 0.6)"
    if bit == 43:
        b = progs.book("fib", 12)
        c0 = rtl.run(b, 4, 4)["cycles"]
        c1 = rtl.run(b, 4, 4, mut=mut)["cycles"]
        return (c1 > 1.3 * c0), f"fib(12) 4x4 cycles {c1} with the mutant vs {c0} (bound: > 1.3x)"
    if bit == 44:
        b = progs.book("treesum", 7)
        l0 = rtl.run(b, 4, 4)["msgs"]["msg_link"]
        l1 = rtl.run(b, 4, 4, mut=mut)["msgs"]["msg_link"]
        return (l1 > 1.3 * l0), f"treesum(7) 4x4 LINK messages {l1} with the mutant vs {l0} (bound: > 1.3x)"
    if bit == 45:
        b = progs.book("qsort", 30)
        c0 = rtl.run(b, 4, 4)["cycles"]
        c1 = rtl.run(b, 4, 4, mut=mut)["cycles"]
        return (c1 > 1.15 * c0), f"qsort(30) 4x4 cycles {c1} with the mutant vs {c0} (bound: > 1.15x)"
    if bit == 46:
        b = progs.book("qsort", 30)
        r0 = rtl.run(b, 4, 4); r1 = rtl.run(b, 4, 4, mut=mut)
        m0 = sum(r0["msgs"].values()) / r0["interactions"]; m1 = sum(r1["msgs"].values()) / r1["interactions"]
        return (m1 > 1.15 * m0), f"qsort(30) 4x4 {m1:.3f} msgs/interaction with the mutant vs {m0:.3f} (bound: > 1.15x)"
    if bit == 47:
        # the step-11 path still gives a fork task popped from an empty stack, so the effect is modest on
        # small meshes (fib(16) 4x4 seed 1: 8,254 vs 7,530 cycles; the simulation is deterministic)
        b = progs.book("fib", 16)
        c0 = rtl.run(b, 4, 4, seed=1)["cycles"]
        c1 = rtl.run(b, 4, 4, seed=1, mut=mut)["cycles"]
        return (c1 > BOUND47 * c0), f"fib(16) 4x4 cycles {c1} with the mutant vs {c0} (bound: > {BOUND47}x)"
    if bit == 49:
        # step 19: without the gradient the short retry timeout livelocks global treesum(9) 3x3 (RTL seeds 3, 10, 11
        # of 30 at +rto=8 stop at ~2,900 of 18,410 interactions); with it all 30 seeds finish
        import test_mempress as tm
        b = progs.book("treesum", 9); W, H = 3, 3
        cells = tuple((x, y) for x in range(W) for y in range(H) if (x, y) != (W - 1, H - 1))
        bad = []; rto0, rg0 = fabric.RTO, fabric.RGRAD; fabric.RTO, fabric.RGRAD = 8, (rg0 or 3)
        for s in (3, 10, 11):
            r = rtl.run(b, W, H, img=tm.ballast_img(b, W, H, 1024, *tm.GKEEP, cells), seed=s, jitter=30, mut=mut, maxcycles=300_000, timeout=600)
            if r["status"] != 0:
                bad.append(s)
        fabric.RTO, fabric.RGRAD = rto0, rg0
        return bool(bad), f"global treesum(9) 3x3 seeds 3/10/11: {len(bad)} stop without progress with the mutant"
    if bit == 50:
        # step 21: default config (+rto=8 +rgrad=3 +rsv=1).  A home cell with zero free node slots (mempress ballast
        # keep 0/8) blocks its ejection port on the first NODE that arrives unless rule d passes it on; the correct
        # design finishes all 10 keep-0 cases, the mutant stops on every one (results/s21/rtl_k0.log)
        import test_mempress as tm
        bad = []
        for name, N, W, H, s in (("fib", 12, 2, 2, 3), ("treesum", 6, 3, 2, 5)):
            b = progs.book(name, N); want = progs.expected(name, N)
            r = rtl.run(b, W, H, img=tm.ballast_img(b, W, H, 1024, 0, 8), seed=s, jitter=30, mut=mut, maxcycles=300_000, timeout=600)
            if r["status"] != 0 or r["readback"] != want:
                bad.append(f"{name}({N}) {W}x{H} status {r['status']}")
        return bool(bad), f"ballast keep 0/8 at the default +rsv=1: {', '.join(bad) or 'none'} stop with the mutant"
    if bit == 51:
        # step 20: the reserve only applies with a neighbour closer to room; a 1x1 cell has none, so fib(10) with
        # exactly the 93 free node / var slots its RTL run needs (results/s20/minkeep_rtl.py) must still finish
        import test_mempress as tm
        b = progs.book("fib", 10); want = progs.expected("fib", 10)
        rg0 = fabric.RGRAD; fabric.RGRAD = rg0 or 3
        r0 = rtl.run(b, 1, 1, img=tm.ballast_img(b, 1, 1, 1024, 93, 93, ((0, 0),)), maxcycles=200_000)
        r1 = rtl.run(b, 1, 1, img=tm.ballast_img(b, 1, 1, 1024, 93, 93, ((0, 0),)), mut=mut, maxcycles=200_000)
        fabric.RGRAD = rg0
        good = r0["status"] == 0 and r0["readback"] == want
        return (good and not (r1["status"] == 0 and r1["readback"] == want)), f"fib(10) 1x1 with 93 free slots: status {r0['status']} correct design, {r1['status']} mutant"
    if bit == 52:
        import test_mempress as tm
        n, fails, tag = tm.run_near(True, mut, verbose=False)
        return bool(fails), (f"{tag}" if fails else f"survived {n} near-overfull cases")
    if bit == 7:
        b = progs.book("treesum_direct", 8)
        c1 = rtl.run(b, 1, 1, mut=mut)["cycles"]
        c4 = rtl.run(b, 4, 4, mut=mut)["cycles"]
        sp = c1 / c4
        return (sp < 3.0), f"treesum_direct(8) speedup 4x4/1x1 = {sp:.2f} (bound >= 3.0)"
    tests = []
    for name, n in PROGS:
        tests.append((f"prog {name}({n})", progs.book(name, n)))
    for name, src, _, _ in test_units.CASES:
        tests.append((f"unit {name}", ir.parse_book(src)))
    for name, src, _ in test_units.LANG:
        tests.append((f"lang {name}", lang.compile_book(src)))
    k = 0
    for i in range(2000):
        if k >= 60: break
        bk = randnet.gen_book(i)
        try: semantic.result(bk, fuel=5000)
        except semantic.OutOfFuel: continue
        tests.append((f"fuzz {i}", bk)); k += 1
    for j, (name, b) in enumerate(tests):
        ref = semantic.result(b, fuel=10**7)
        for (W, H) in ((2, 2), (1, 1)):
            img = fabric.Image(b, W, H, 1024, 1024, scatter=j if W > 1 else None)
            try:
                r = rtl.run(b, W, H, img=img, seed=j + 1, jitter=30, mut=mut, maxcycles=2_000_000, timeout=120)
            except Exception as e:
                return True, f"{name} on {W}x{H}: simulator error {str(e)[:80]}"
            if not same(r, ref):
                return True, f"{name} on {W}x{H}: got {r['readback'][:60]} / {r['interactions']} interactions / {r['node_count']} nodes, want {ref['readback'][:60]} / {ref['interactions']} / {ref['nodes']}"
    return False, f"survived {len(tests)} tests"


if __name__ == "__main__":
    bits = [int(x) for x in sys.argv[1:]] or sorted(MUTANTS)
    caught = 0
    for bit in bits:
        ok, why = try_mutant(bit)
        caught += ok
        print(f"mutant {bit:2d} {'CAUGHT ' if ok else 'SURVIVED'} {MUTANTS[bit]} -- {why}", flush=True)
    print(f"mutants: {caught}/{len(bits)} caught")
    sys.exit(0 if caught == len(bits) else 1)
