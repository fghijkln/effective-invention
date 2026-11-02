"""Step 29 RTL validation of the placement certificate (omega/placement.py, SPEC §7.8).

Every run is a configuration the certificate accepts (unless marked `claim: False`), on RTL with +pcert=rgrad:
the job must finish with the right answer and the semantic interaction count, the simulation audit must count zero
cycles in which some cell has no cell with >= lm_hi free node and var slots within rgrad hops (pcert_viol), and the
mesh-wide live load must stay <= (L_n, L_v).  Per-cell peaks are recorded.  Resumable: one JSON line per run in
results/s29/val_<set>.jsonl, already-done keys are skipped.

usage: validate.py SET   (SET: small | hetero | big | big4)
"""
import sys, os, json, time, random
sys.setrecursionlimit(100000)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "tests"))
from omega import rtl, progs, eal, placement, fabric
import test_mempress as tm

OUT = os.path.join(os.path.dirname(__file__))
KNOBS = [dict(seed=1), dict(seed=2, jitter=30), dict(seed=3, stall=30), dict(seed=4, jitter=60, stall=20, pmsg=32),
         dict(seed=5, extra=["+ilr=2"]), dict(seed=6, jitter=20, extra=["+s14=0", "+rto=32"])]
_B = {}


def bound(name, N):
    k = (name, N)
    if k not in _B:
        book = progs.book(name, N)
        _B[k] = (book, eal.bound(book))
    return _B[k]


def one(key, name, N, W, H, r, S, knob, keep=None, claim=True, Sbuild=None, maxcycles=8_000_000, timeout=3000):
    book, b = bound(name, N)
    Ln, Lv = b["B_nodes"], b["B_vars"]
    cs = placement.cells(W, H)
    Sb = Sbuild or S
    if keep is None and Sb == S:
        img = None; fn = fv = None
        cert = placement.certify(W, H, Ln, Lv, S=S, r=r)
        nball = 0
    else:
        keep = keep or {c: S for c in cs}
        img = fabric.Image(book, W, H, Sb, 1024)
        nball = 0
        from omega.ports import mk, ERA, NONE
        for c in cs:
            fnl = [s for s in range(Sb) if img.nodes[c][s] is None]
            fvl = [s for s in range(Sb) if img.vars[c][s] is None]
            for s in fnl[keep[c]:]:
                img.nodes[c][s] = [mk(ERA), mk(ERA)]; img.nown[c][s] = 14; nball += 1
            for s in fvl[keep[c]:]:
                img.vars[c][s] = mk(NONE); img.vown[c][s] = 14
        fn = fv = dict(keep)
        cert = placement.certify(W, H, Ln, Lv, free_n=fn, free_v=fv, S=S, r=r)
    wit = placement.witness(W, H, Ln, Lv, free_n=fn, free_v=fv, S=S, r=r) if W * H <= 16 else None
    kn = dict(knob)
    extra = [f"+pcert={r}", f"+rgrad={r}"] + kn.pop("extra", [])
    t = time.time()
    res = rtl.run(book, W, H, slots=Sb, img=img, maxcycles=maxcycles, timeout=timeout, extra=extra, **kn)
    want = progs.expected(name, N)
    used0 = (W * H * Sb - (sum(keep.values()) if keep else W * H * Sb))      # ballast + nothing else at cycle 0
    pk = {f"{x},{y}": (c.get("peak_nodes", 0) - (Sb - keep[(x, y)] if keep else 0), c.get("peak_vars", 0) - (Sb - keep[(x, y)] if keep else 0))
          for (x, y), c in res["cells"].items()}           # job's own per-cell peak (ballast taken off)
    rec = {"key": key, "prog": name, "N": N, "mesh": f"{W}x{H}", "rgrad": r, "S": S, "S_build": Sb, "knob": knob,
           "claim": claim, "cert": cert, "witness": wit is not None, "L": (Ln, Lv), "status": res["status"],
           "ok": res["status"] == 0 and res["readback"] == want and res.get("interactions") == b["interactions"],
           "readback": str(res["readback"])[:40], "cycles": res.get("cycles"), "pcert_viol": res.get("pcert_viol"),
           "pcert_min": res.get("pcert_min"),
           "live_peak": (res.get("pcert_used_n", 0) - used0, res.get("pcert_used_v", 0) - used0),
           "cell_peak_max": (max(v[0] for v in pk.values()), max(v[1] for v in pk.values())),
           "secs": round(time.time() - t, 1)}
    rec["sound"] = (not claim) or (rec["ok"] and rec["pcert_viol"] == 0 and rec["live_peak"][0] <= Ln and rec["live_peak"][1] <= Lv)
    return rec


def jobs_small():
    tab = json.load(open(os.path.join(OUT, "cert_table.json")))
    meshes = [("2x2", 2, 2, 3), ("3x3", 3, 3, 3), ("3x3 rgrad 4", 3, 3, 4), ("4x4 rgrad 6", 4, 4, 6)]
    for p in ["sum", "list", "higher", "fib", "treesum", "treesum_direct", "sort", "qsort_l"]:
        n1 = tab[p]["nmax"]["1x1 S=1024"]
        for mname, W, H, r in meshes:
            N = tab[p]["nmax"][f"{mname} S=1024"]
            for k, kn in enumerate(KNOBS):
                yield (f"{p}({N}) {W}x{H} r{r} S1024 k{k}", dict(name=p, N=N, W=W, H=H, r=r, S=1024, knob=kn), n1)


def jobs_hetero():
    """3x3 x 1024 with ballast: poor cells (free 6..40 < lm_hi) and a few rich ones; small programs.  Fixed cases
    (corner room: certified at rgrad 4, not at 3) and random shapes; uncertified ones are run with claim False."""
    W = H = 3
    cs = placement.cells(W, H)
    fixed = []
    corner = {c: 8 for c in cs}; corner[(2, 2)] = 1024
    centre = {c: 8 for c in cs}; centre[(1, 1)] = 1024
    two = {c: 8 for c in cs}; two[(2, 0)] = 600; two[(0, 2)] = 600
    for name, N in (("fib", 7), ("treesum", 4), ("sum", 60), ("list", 12)):
        for r in (3, 4):
            fixed.append(("corner", corner, name, N, r))
        fixed.append(("centre", centre, name, N, 3))
        fixed.append(("two", two, name, N, 3))
    for tag, keep, name, N, r in fixed:
        for k, kn in enumerate(KNOBS[:4]):
            yield (f"{tag} {name}({N}) r{r} k{k}", dict(name=name, N=N, W=W, H=H, r=r, S=1024, knob=kn, keep=keep), None)
    rnd = random.Random(29)
    progsN = [("fib", 6), ("fib", 8), ("treesum", 4), ("treesum", 5), ("treesum_direct", 6), ("sum", 40), ("list", 10), ("higher", 10), ("qsort_l", 4), ("sort", 5)]
    for i in range(60):
        keep = {c: (rnd.randint(4, 40) if rnd.random() < 0.6 else rnd.randint(64, 1024)) for c in cs}
        name, N = rnd.choice(progsN)
        r = rnd.choice((2, 3, 4))
        kn = dict(rnd.choice(KNOBS)); kn["seed"] = 100 + i
        yield (f"rand{i} {name}({N}) r{r}", dict(name=name, N=N, W=W, H=H, r=r, S=1024, knob=kn, keep=keep), None)


def jobs_big():
    """The benchmark sizes on the smallest homogeneous cell that certifies them (fib(20) / treesum_direct(14): no
    65,536-slot cell does on 1x1), 2x2 / 3x3 / 4x4 (rgrad 6), six knob sets each; cells built at Sb, ballast leaves S free."""
    bench = [("fib", 20), ("treesum_direct", 14), ("treesum", 9), ("qsort_l", 40), ("sort", 20), ("list", 120), ("higher", 100), ("sum", 1000), ("fact", 20),
             ("fib", 19), ("treesum_direct", 13)]
    for W, H, r, Sb in ((3, 3, 3, 65536), (4, 4, 6, 32768), (2, 2, 3, 65536)):
        for name, N in bench:
            book, b = bound(name, N)
            S = placement.min_slots(W, H, b["B_nodes"], b["B_vars"], r=r)
            if S is None or S > Sb: continue
            cs = placement.cells(W, H)
            for k, kn in enumerate(KNOBS):
                yield (f"{name}({N}) {W}x{H} r{r} S{S} k{k}", dict(name=name, N=N, W=W, H=H, r=r, S=S, knob=kn,
                                                                  keep={c: S for c in cs}, Sbuild=Sb), None)


def main(which):
    path = os.path.join(OUT, f"val_{which}.jsonl")
    done = set()
    if os.path.exists(path):
        for line in open(path):
            try: done.add(json.loads(line)["key"])
            except Exception: pass
    gen = {"small": jobs_small, "hetero": jobs_hetero, "big": jobs_big}[which]
    for key, kw, n1 in gen():
        if key in done: continue
        keep = kw.pop("keep", None)
        book, b = bound(kw["name"], kw["N"])
        claim = True
        if keep is not None:
            claim = placement.certify(kw["W"], kw["H"], b["B_nodes"], b["B_vars"], free_n=keep, free_v=keep, S=kw["S"], r=kw["r"])
        try:
            rec = one(key, keep=keep, claim=claim, **kw)
        except Exception as e:
            rec = {"key": key, "error": f"{type(e).__name__}: {e}"[:300], "sound": False, "claim": claim}
        if n1 is not None: rec["N_1x1"] = n1
        with open(path, "a") as f: f.write(json.dumps(rec) + "\n")
        print(json.dumps(rec), flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
