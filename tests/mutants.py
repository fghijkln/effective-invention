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
    27: "memory pressure: roomy neighbours ignored (no PULL / NODE offload, OOM SPAWNs round robin)",
    28: "memory pressure: hungry does not require roomy (a full cell still asks for work)",
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
}
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
    if bit in (27, 28):
        import test_mempress
        n, fails, tag = test_mempress.run_cases(True, mut, verbose=False, quick=True)
        return bool(fails), (f"{tag}: wrong result / timeout" if fails else f"survived {n} memory-pressure cases")
    if bit == 37:
        b = progs.book("fib", 12)
        c0 = rtl.run(b, 1, 1)["cycles"]
        c1 = rtl.run(b, 1, 1, mut=mut)["cycles"]
        return (c1 > 1.1 * c0), f"fib(12) 1x1 cycles {c1} with the mutant vs {c0} (bound: > 1.1x)"
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
