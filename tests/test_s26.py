"""Step 26 tests: memory-bound admission control in the RTL (rtl/omega_adm.sv, omega/adm_rtl.py, SPEC §7.5),
cross-checked against the fabric-model scheduler (omega/admission.py, step 25) on the same job lists.

For every scenario both run the same jobs with the same budget (slots - margin) and must agree on
* the decisions: the same jobs rejected, the same FIFO start order (and nothing else started);
* the outcome: status ok, no stall / blocked controller, every admitted job done with its known answer;
* the work: the same total interaction count (schedule independent per job, so equal sums);
and the RTL run is audited every cycle by the controller (live nodes / vars <= reserved while no untyped job runs,
reserved <= budget, on a mesh every cell keeps the margin free), no two jobs of one owner overlap.
Without admission (every job loaded at cycle 0, adm off) the RTL flood stops (status 3, no progress).

usage: test_s26.py [--quick | --ci] [--mutants] [--json FILE]
"""
import sys, os, time, json, subprocess
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
from omega import admission, adm_rtl, progs

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
SMALL = [("sum", 30), ("fib", 5), ("treesum_direct", 4), ("treesum", 3), ("higher", 4), ("fact", 20)]
TINY = [("fib", 5), ("treesum_direct", 4), ("fact", 12), ("sum", 10), ("fib", 4), ("treesum_direct", 3)]
MUT = int(os.environ.get("OMEGA_S26_MUT", "0"))      # RTL mutant bit (60-64) for --mutants
passed = failed = 0
out = {}


def ok(cond, msg):
    global passed, failed
    if cond: passed += 1
    else:
        failed += 1; print("FAIL", msg, flush=True)
    return cond


def mkjobs(specs, owners=None, bound="W"):
    return [admission.Job(f"{n}({N})", progs.source(n, N), owners[k] if owners else k % 15, bound=bound)
            for k, (n, N) in enumerate(specs)]


def cross(label, specs, W, H, S, bound="W", owners=None, seed=1):
    t = time.time()
    pj = mkjobs(specs, owners, bound)
    sch = admission.Scheduler(pj, W, H, S, admit=True, dedupe=True)
    rp = sch.run(audit=True)
    tp = time.time() - t
    rj = mkjobs(specs, owners, bound)
    rr = adm_rtl.run_admitted(rj, W, H, S, seed=seed, mut=MUT, noprog=200000, maxcycles=8_000_000)
    tr = time.time() - t - tp
    exp = [progs.expected(n, N) for n, N in specs]
    p_rej = sorted(k for k, j in enumerate(rp["jobs"]) if j["state"] == "rejected")
    r_rej = sorted(k for k, j in enumerate(rr["jobs"]) if j["state"] == "rejected")
    p_order = [k for k in sorted((k for k, j in enumerate(rp["jobs"]) if j["start"] is not None),
                                 key=lambda k: (rp["jobs"][k]["start"], k))]
    r_order = [e[1] for e in rr["events"] if e[0] == "start"]
    adm = [k for k in range(len(specs)) if k not in r_rej]
    r_ok = sum(1 for k in adm if rr["jobs"][k]["state"] == "done" and rr["jobs"][k]["result"] == exp[k])
    p_ok = sum(1 for k in adm if rp["jobs"][k]["result"] == exp[k])
    overlap = []
    for o in {j["owner"] for j in rr["jobs"]}:
        iv = sorted((j["start"], j["end"] if j["end"] is not None else 1 << 60) for j in rr["jobs"] if j["owner"] == o and j["start"] is not None)
        overlap += [o for a, b in zip(iv, iv[1:]) if b[0] < a[1]]
    rec = {"python": {"status": rp["status"], "cycles": rp["cycles"], "interactions": rp["interactions"], "correct": p_ok,
                      "rejected": len(p_rej), "max_reserved": rp["max_reserved"], "peak_live": rp["peak_live"], "violation": rp["violation"]},
           "rtl": {"status": rr["status"], "cycles": rr["cycles"], "interactions": rr["interactions"], "correct": r_ok,
                   "rejected": len(r_rej), "max_reserved": rr.get("max_reserved"), "peak_live": rr.get("peak_live"),
                   "nviol": rr.get("nviol"), "viol": rr["viol"][:1], "blocked": rr["blocked"]},
           "admitted": len(adm), "budget": rr["budget"], "secs": [round(tp, 1), round(tr, 1)]}
    out[label] = rec
    ok(rp["status"] == "ok" and p_ok == len(adm) and rp["violation"] is None, f"{label}: python {rp['status']} {p_ok}/{len(adm)} {rp['violation']}")
    ok(rr["status"] == 0 and not rr["blocked"] and r_ok == len(adm), f"{label}: rtl status {rr['status']} blocked {rr['blocked']} {r_ok}/{len(adm)} correct")
    ok(r_rej == p_rej, f"{label}: rejected rtl {r_rej} vs python {p_rej}")
    ok(r_order == p_order, f"{label}: start order differs (rtl {r_order[:12]}... python {p_order[:12]}...)")
    ok(rr["interactions"] == rp["interactions"], f"{label}: interactions rtl {rr['interactions']} vs python {rp['interactions']}")
    ok(rr.get("nviol") == 0, f"{label}: rtl audit violations {rr.get('nviol')} first {rr['viol'][:1]}")
    ok(rr.get("max_reserved") is not None and rr["max_reserved"][0] <= rr["budget"][0] and rr["max_reserved"][1] <= rr["budget"][1],
       f"{label}: max reserved {rr.get('max_reserved')} > budget {rr['budget']}")
    ok(not overlap, f"{label}: jobs of one owner overlap (owners {sorted(set(overlap))})")
    print(f"  {label}: {W}x{H} x {S}, {len(specs)} jobs ({bound}): rejected {len(r_rej)} (python {len(p_rej)}); "
          f"rtl {rr['status']} {r_ok}/{len(adm)} correct in {rr['cycles']} cycles, peak live {rr.get('peak_live')}, "
          f"max reserved {rr.get('max_reserved')} of {rr['budget']}; python {rp['status']} {p_ok}/{len(adm)} in {rp['cycles']} cycles; "
          f"interactions {rr['interactions']} / {rp['interactions']} ({tr:.0f}s rtl, {tp:.0f}s python)", flush=True)
    return rp, rr


def static(label, specs, W, H, S):
    t = time.time()
    r = adm_rtl.run_static(mkjobs(specs), W, H, S, noprog=20000)
    exp = [progs.expected(n, N) for n, N in specs]
    good = sum(1 for a, b in zip(r["results"], exp) if a == b)
    out[label] = {"status": r["status"], "cycles": r["cycles"], "interactions": r["interactions"], "correct": good}
    ok(r["status"] == 3, f"{label}: without admission expected status 3 (no progress), got {r['status']}")
    print(f"  {label}: {W}x{H} x {S}, {len(specs)} jobs loaded at cycle 0, adm off: status {r['status']} after {r['cycles']} cycles "
          f"({r['interactions']} interactions) ({time.time() - t:.0f}s)", flush=True)


def main(argv):
    t0 = time.time()
    quick = "--quick" in argv
    if "--mutants" in argv:
        return mutants()
    print("step 26: admission control in RTL vs the fabric model", flush=True)
    flood = (SMALL * 30)[:180]
    cross("flood_2x2_W", flood, 2, 2, 280)
    if "--ci" in argv:                                   # CI subset: one flood on a mesh, one cell
        cross("one_cell", TINY * 4, 1, 1, 150)
        print(f"step 26 tests: {passed}/{passed + failed} pass ({time.time() - t0:.0f}s)", flush=True)
        return 0 if failed == 0 else 1
    if not quick:
        cross("flood_2x2_W_seed2", flood, 2, 2, 280, seed=2)
        cross("flood_2x2_B", flood, 2, 2, 280, bound="B")
        cross("flood_3x3_W", (SMALL * 50)[:300], 3, 3, 280)
    cross("reject", [("treesum", 9)] + TINY * 3, 2, 2, 200)
    rp, rr = cross("queue", [("treesum", 5)] + SMALL * 3, 2, 2, 1100)
    t5 = rr["jobs"][0]["end"]
    ok(t5 is not None and all(j["start"] is not None and j["start"] >= t5 for j in rr["jobs"][1:]), f"queue: rtl starts before treesum(5) ends at {t5}")
    rp, rr = cross("untyped", [("qsort", 8)] + SMALL * 2, 2, 2, 280)
    ok(not rr["jobs"][0]["typed"] and rr["events"] and rr["events"][0][:2] == ("start", 0), "untyped: qsort is not started first")
    cross("one_cell", TINY * 4, 1, 1, 150)
    cross("owners", TINY * 3, 2, 2, 600, owners=[k // 2 % 3 for k in range(18)])
    if not quick and not MUT:
        static("static_flood_2x2", flood, 2, 2, 280)
        static("static_flood_3x3", (SMALL * 50)[:300], 3, 3, 280)
    if "--json" in argv:
        with open(argv[argv.index("--json") + 1], "w") as f: json.dump(out, f, indent=1, default=str)
    print(f"step 26 tests: {passed}/{passed + failed} pass ({time.time() - t0:.0f}s)", flush=True)
    return 0 if failed == 0 else 1


MUTANTS = {60: "admission ignores the running jobs' reservations", 61: "no reject check (over-budget jobs admitted)",
           62: "two jobs of one owner may run at once", 63: "root var not reset before a start",
           64: "reservations never released"}


def mutants():
    caught = 0
    only = [int(x) for x in os.environ.get("OMEGA_S26_ONLY", "").split(",") if x]
    sel = {m: w for m, w in MUTANTS.items() if not only or m in only}
    for m, what in sel.items():
        env = dict(os.environ, OMEGA_S26_MUT=str(1 << m), PYTHONPATH=f"{ROOT}:{HERE}")
        p = subprocess.run([sys.executable, __file__, "--quick"], env=env, capture_output=True, text=True, timeout=5400)
        c = p.returncode != 0
        caught += c
        first = next((l for l in p.stdout.splitlines() if l.startswith("FAIL")), p.stderr[-300:])
        print(f"  mutant {m} ({what}): {'caught' if c else 'NOT caught'}  [{first[:160]}]", flush=True)
    ok(caught == len(sel), f"mutants: {caught}/{len(sel)} caught")
    print(f"s26 mutants: {caught}/{len(sel)} caught", flush=True)
    return 0 if caught == len(sel) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
