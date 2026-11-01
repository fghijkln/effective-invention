"""Step 28 tests: a 16-bit slot field (cells of up to 65,536 node + 65,536 var slots, SPEC §2.1 / §7.7) and the
benchmark sizes it certifies.

* encoding: addr / addr_slot round trip for every slot bit; a slot >= 4096 lives in payload bits [15:12] (unused, and
  required to be 0, before step 28);
* high slots on a mesh: every cell's low slots filled with ballast so that all allocation lands in slots >= 4096
  (up to 16,383 / 65,535); RTL and fabric model equal the semantic reducer (readback, interactions, nodes);
* forged pointers with slot bits [15:12] set on 1024-slot cells are out of bounds (TRAP_OOB) in all three models;
* certification at the benchmark sizes: every Ω-L benchmark whose bound fits a 65,536-slot cell runs on RTL 1x1 with
  exactly B_nodes / B_vars free slots (qsort_l(40), list(120), sum(1000), sort(20), higher(100), treesum(9),
  fact(20); the largest fib / treesum_direct / treesum that fit: fib(17), treesum_direct(12), treesum(10)) and on a
  2x2 mesh with slots_mesh free slots in every cell (treesum(9), qsort_l(40), sum(1000));
* admission with big cells: the step-26 controller with a root pool above slot 4096 (2x2 x 20,000 slots) admits
  the benchmark-size jobs one after another, cross-checked against the fabric-model scheduler;
* fib(20) and treesum_direct(14) stay uncertifiable (B > 65,536), checked as such.

usage: test_s28.py [--quick | --ci] [--mutants] [--json FILE]   (--ci: encoding, forged pointers, one high-slot run)
"""
import sys, os, time, json, subprocess
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
from omega import eal, progs, fabric, semantic, rtl, admission, adm_rtl
from omega.ports import *
import test_eal as TE
import test_security as TS

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
MUT = int(os.environ.get("OMEGA_S28_MUT", "0"))
MAXS = 65536
passed = failed = 0
out = {}


def ok(cond, msg):
    global passed, failed
    if cond: passed += 1
    else:
        failed += 1; print("FAIL", msg, flush=True)
    return cond


def encoding():
    for s in [0, 1, 4095, 4096, 4097, 0x1234, 0x8000, 0xFFFF] + [1 << k for k in range(16)]:
        for x, y in ((0, 0), (3, 5), (15, 15)):
            a = addr(x, y, s)
            ok(addr_slot(a) == s and addr_xy(a) == (x, y) and a >> 24 == 0, f"addr round trip ({x}, {y}, {s})")
    p = mk(VAR, 0, addr(1, 2, 0x5ABC), owner=3)
    ok(tag(p) == VAR and owner(p) == 3 and addr_slot(payload(p)) == 0x5ABC, "VAR port with a 16-bit slot")
    print("  encoding: addr / addr_slot round trip over all 16 slot bits", flush=True)


def ballast_high(book, W, H, slots, keep):
    """Fill every free node / var slot except the `keep` highest ones, so allocation only uses high slots."""
    img = fabric.Image(book, W, H, slots, 1024)
    for c in img.nodes:
        fn = [s for s in range(slots) if img.nodes[c][s] is None]
        fv = [s for s in range(slots) if img.vars[c][s] is None]
        for s in fn[:len(fn) - keep]:
            img.nodes[c][s] = [mk(ERA), mk(ERA)]; img.nown[c][s] = 14
            img.n_ballast = getattr(img, "n_ballast", 0) + 1
        for s in fv[:len(fv) - keep]:
            img.vars[c][s] = mk(NONE); img.vown[c][s] = 14
    return img


def high_slots(quick, ci=False):
    cases = [("fib", 10, 2, 2, 8192, 600, 1), ("treesum", 6, 2, 2, 8192, 1500, 2), ("qsort", 15, 2, 2, 16384, 800, 3),
             ("list", 20, 3, 2, 8192, 600, 4)]
    if ci: cases = cases[:1]
    if not quick and not ci: cases += [("sort", 10, 2, 2, 65536, 1200, 5), ("treesum_direct", 7, 2, 2, 8192, 600, 6), ("higher", 12, 1, 1, 65536, 2000, 7)]
    for name, N, W, H, S, keep, seed in cases:
        book = progs.book(name, N)
        ref = semantic.result(book)
        want = progs.expected(name, N)
        if MUT == 0:
            f = fabric.Fabric(book, W, H, slots=S, seed=seed, p_jitter=0.1, img=ballast_high(book, W, H, S, keep)).run()
            ok(f.readback() == want and f.interactions == ref["interactions"], f"fabric {name}({N}) {W}x{H} x {S} high slots: {f.readback()} {f.interactions}")
        img = ballast_high(book, W, H, S, keep)
        r = rtl.run(book, W, H, slots=S, img=img, seed=seed, jitter=30, mut=MUT, maxcycles=3_000_000, timeout=900)
        hi = min(c.get("peak_nodes", 0) for c in r["cells"].values()) if r.get("cells") else 0
        ok(r["status"] == 0 and r["readback"] == want and r["interactions"] == ref["interactions"] and r.get("node_count") == img.n_ballast + ref["nodes"],
           f"RTL {name}({N}) {W}x{H} x {S} high slots: status {r['status']} {r.get('readback')} {r.get('interactions')} / {ref['interactions']} nodes {r.get('node_count')} - {img.n_ballast} ballast vs {ref['nodes']}")
        out[f"high_{name}_{N}_{W}x{H}_{S}"] = {"status": r["status"], "cycles": r.get("cycles"), "interactions": r.get("interactions")}
        print(f"  high slots {name}({N}) {W}x{H} x {S} (only the top {keep} slots free; allocation in slots {S - keep}..{S - 1}): "
              f"RTL status {r['status']}, {r.get('cycles')} cycles, {r.get('readback')}", flush=True)


def forged():
    cases = [("forged var with slot bits [15:12] = 1", "@main = r & #7 ~ r & !var(0,0,4100) ~ #1"),
             ("forged var at slot 65,535", "@main = r & #7 ~ r & !var(0,0,65535) ~ #1"),
             ("forged node with slot 0xF000", "@main = r & #7 ~ r & * ~ !con(0,0,61440)")]
    for name, src in cases:
        b, t = TS.build([(1, progs.book("fib", 8)), (9, TS.attacker(src))])
        good, ref, r = TS.check(name, b, t, 2, 2, use_rtl=True, seed=1, mut=MUT, want=[progs.expected("fib", 8), None], verbose=True)
        reasons = {x for x, _ in ref["traps"]}
        ok(good and reasons == {TRAP_OOB}, f"{name}: traps {ref['traps']} (want OOB) rtl {r and r.get('traps')}")
    print("  forged pointers with slot bits >= 4096 on 1024-slot cells: OOB in semantic, fabric and RTL", flush=True)


SUITE = [("qsort_l", 40), ("list", 120), ("sum", 1000), ("sort", 20), ("higher", 100), ("treesum", 9), ("fact", 20),
         ("fib", 17), ("treesum_direct", 12), ("treesum", 10)]
NOFIT = [("fib", 20), ("treesum_direct", 14)]


QD = 4096        # task-stack depth for the certification runs (B bounds slots, not the task stack: SPEC §7.2)


def at_bound(book, b, want, slots, seed=3):
    """RTL 1x1, `slots` slots, ballast leaving exactly B_nodes - n0 / B_vars - v0 free (as test_eal.rtl_at_bound, deeper task stack)."""
    kn, kv = b["B_nodes"] - b["n0"], b["B_vars"] - b["v0"]
    r = rtl.run(book, 1, 1, slots=slots, qdepth=QD, img=TE.ballast(book, 1, 1, slots, kn, kv), seed=seed, mut=MUT, maxcycles=6_000_000, timeout=1500)
    c = r["cells"].get((0, 0), {})
    pn = c.get("peak_nodes", 0) - (slots - kn - b["n0"]); pv = c.get("peak_vars", 0) - (slots - kv - b["v0"])
    return r["status"] == 0 and r["readback"] == want, pn, pv, r.get("cycles"), r["status"], c.get("maxq")


def at_mesh(book, b, want, W=2, H=2, seed=5):
    k = b["slots_mesh"]
    r = rtl.run(book, W, H, slots=k, qdepth=QD, img=TE.ballast(book, W, H, k, k, k), seed=seed, jitter=30, mut=MUT, maxcycles=6_000_000, timeout=1500)
    return r["status"] == 0 and r["readback"] == want, r["status"], r.get("cycles")


def certify(quick):
    rows = {}
    suite = SUITE if not quick else [("qsort_l", 40), ("treesum", 9), ("fact", 20)]
    for name, N in suite:
        book = progs.book(name, N)
        ok(eal.check(progs.source(name, N))["ok"], f"{name}({N}) not in Ω-L")
        b = eal.bound(book)
        S = max(b["B_nodes"], b["B_vars"])
        ok(S <= MAXS, f"{name}({N}): B {S} > {MAXS}")
        t = time.time()
        good, pn, pv, cyc, st, mq = at_bound(book, b, progs.expected(name, N), S)
        ok(good and pn <= b["B_nodes"] and pv <= b["B_vars"], f"RTL 1x1 at B {name}({N}): status {st} peak ({pn}, {pv}) B ({b['B_nodes']}, {b['B_vars']})")
        rows[f"{name}({N})"] = {"B": (b["B_nodes"], b["B_vars"]), "slots_1x1": b["slots_1x1"], "slots_mesh": b["slots_mesh"],
                                "rtl_1x1": {"status": st, "peak": (pn, pv), "cycles": cyc, "max_task_stack": mq}}
        print(f"  certified {name}({N}) on RTL 1x1 with exactly B = ({b['B_nodes']}, {b['B_vars']}) free slots: status {st}, "
              f"peak ({pn}, {pv}) = B / ({b['B_nodes'] / max(pn, 1):.0f}, {b['B_vars'] / max(pv, 1):.0f}), task stack {mq}, {cyc} cycles ({time.time() - t:.0f}s)", flush=True)
    for name, N in ((("treesum", 9), ("qsort_l", 40), ("sum", 1000)) if not quick else (("qsort_l", 40),)):
        book = progs.book(name, N); b = eal.bound(book)
        t = time.time()
        good, st, cyc = at_mesh(book, b, progs.expected(name, N))
        ok(good, f"RTL 2x2 with slots_mesh = {b['slots_mesh']} per cell, {name}({N}): status {st}")
        rows.setdefault(f"{name}({N})", {})["rtl_2x2_mesh"] = {"slots": b["slots_mesh"], "status": st, "cycles": cyc}
        print(f"  certified {name}({N}) on RTL 2x2 with slots_mesh = {b['slots_mesh']} free slots in every cell: status {st}, {cyc} cycles ({time.time() - t:.0f}s)", flush=True)
    for name, N in NOFIT:
        b = eal.bound(progs.book(name, N))
        ok(b["slots_1x1"] > MAXS, f"{name}({N}) should not fit a 65,536-slot cell: {b['slots_1x1']}")
        rows[f"{name}({N})"] = {"B": (b["B_nodes"], b["B_vars"]), "slots_1x1": b["slots_1x1"], "fits": False}
        print(f"  {name}({N}): B = ({b['B_nodes']}, {b['B_vars']}) > 65,536: not certifiable on one cell", flush=True)
    out["certify"] = rows


def big_admission(quick):
    specs = [("treesum", 9), ("qsort_l", 40), ("list", 120), ("sum", 1000), ("sort", 20), ("higher", 100), ("fact", 20)]
    if quick: specs = [("treesum", 8), ("qsort_l", 20), ("sum", 300), ("fact", 20)]
    W = H = 2; S = 20000
    t = time.time()
    pj = [admission.Job(f"{n}({N})", progs.source(n, N), k + 1) for k, (n, N) in enumerate(specs)]
    rp = admission.Scheduler(pj, W, H, S, admit=True, dedupe=True).run(audit=True)
    tp = time.time() - t
    rj = [admission.Job(f"{n}({N})", progs.source(n, N), k + 1) for k, (n, N) in enumerate(specs)]
    rr = adm_rtl.run_admitted(rj, W, H, S, seed=1, mut=MUT, noprog=200000, maxcycles=20_000_000)
    exp = [progs.expected(n, N) for n, N in specs]
    r_ok = sum(1 for k, j in enumerate(rr["jobs"]) if j["state"] == "done" and j["result"] == exp[k])
    p_order = sorted((k for k, j in enumerate(rp["jobs"]) if j["start"] is not None), key=lambda k: (rp["jobs"][k]["start"], k))
    r_order = [e[1] for e in rr["events"] if e[0] == "start"]
    ok(rp["status"] == "ok" and rp["violation"] is None, f"big admission: python {rp['status']} {rp['violation']}")
    ok(rr["status"] == 0 and not rr["blocked"] and r_ok == len(specs), f"big admission: rtl status {rr['status']} blocked {rr['blocked']} {r_ok}/{len(specs)}")
    ok(r_order == p_order and rr["interactions"] == rp["interactions"], f"big admission: order {r_order} vs {p_order}, interactions {rr['interactions']} vs {rp['interactions']}")
    ok(rr.get("nviol") == 0, f"big admission: audit violations {rr.get('nviol')} {rr['viol'][:1]}")
    out["big_admission"] = {"jobs": [n for n in specs], "budget": rr["budget"], "rtl_cycles": rr["cycles"], "python_cycles": rp["cycles"],
                            "interactions": rr["interactions"], "max_reserved": rr.get("max_reserved"), "peak_live": rr.get("peak_live")}
    print(f"  admission with 2x2 x {S} cells (root pool at slots {S}..{S + 15}): {r_ok}/{len(specs)} jobs correct, start order {r_order} "
          f"= model, {rr['interactions']} interactions, {rr['cycles']} cycles (model {rp['cycles']}), max reserved {rr.get('max_reserved')} "
          f"of {rr['budget']}, peak live {rr.get('peak_live')} ({time.time() - t:.0f}s)", flush=True)


def main(argv):
    t0 = time.time()
    quick = "--quick" in argv
    ci = "--ci" in argv
    if "--mutants" in argv:
        return mutants()
    print("step 28: 16-bit slot field, certified benchmark sizes", flush=True)
    encoding()
    forged()
    high_slots(quick, ci)
    if not ci:
        certify(quick)
        big_admission(quick)
    if "--json" in argv:
        with open(argv[argv.index("--json") + 1], "w") as f: json.dump(out, f, indent=1, default=str)
    print(f"step 28 tests: {passed}/{passed + failed} pass ({time.time() - t0:.0f}s)", flush=True)
    return 0 if failed == 0 else 1


MUTANTS = {65: "allocated slot addresses truncated to 12 bits", 66: "out-of-bounds check on slot bits [11:0] only"}


def mutants():
    caught = 0
    for m, what in MUTANTS.items():
        env = dict(os.environ, OMEGA_S28_MUT=str(1 << m), PYTHONPATH=f"{ROOT}:{HERE}")
        p = subprocess.run([sys.executable, __file__, "--quick"], env=env, capture_output=True, text=True, timeout=7200)
        c = p.returncode != 0
        caught += c
        first = next((l for l in p.stdout.splitlines() if l.startswith("FAIL")), p.stderr[-300:])
        print(f"  mutant {m} ({what}): {'caught' if c else 'NOT caught'}  [{first[:160]}]", flush=True)
    ok(caught == len(MUTANTS), f"mutants: {caught}/{len(MUTANTS)} caught")
    print(f"s28 mutants: {caught}/{len(MUTANTS)} caught", flush=True)
    return 0 if caught == len(MUTANTS) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
