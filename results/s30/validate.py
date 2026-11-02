"""Step 30 RTL validation of the joint-load certificate with the task stack (omega/joint.py, SPEC §7.9).

Every claimed run is a configuration `joint.certified` accepts for the concrete job (per-instance loads: W_nodes,
B_vars, hull, Q, plus the engine margin) and the built QDEPTH.  It must finish with the right answer and the semantic
interaction count, both simulation audits must be clean (+pcert: no cell without a roomy cell within rgrad hops;
+tcert: stored task entries <= used_n + 2 used_v + A every cycle), the mesh-wide live load must stay inside the loads
(nodes <= W_nodes + margin, vars <= B_vars, every hull line), and the task entries inside Q.  Runs with claim False
are uncertified configurations (the `boundary` set tries to make them stall).  Resumable, one JSON line per run in
results/s30/val_<set>.jsonl.

usage: validate.py SET   (SET: small | hetero | big | boundary)
"""
import sys, os, json, time, random
from fractions import Fraction as F
sys.setrecursionlimit(1000000)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from omega import rtl, progs, eal, placement, fabric, joint

OUT = os.path.dirname(__file__)
KNOBS = [dict(seed=1), dict(seed=2, jitter=30), dict(seed=3, stall=30), dict(seed=4, jitter=60, stall=20, pmsg=32),
         dict(seed=5, extra=["+ilr=2"]), dict(seed=6, jitter=20, extra=["+s14=0", "+rto=32"])]
_L = {}


def loads(name, N):
    k = (name, N)
    if k not in _L:
        book = progs.book(name, N)
        _L[k] = (book, joint.loads(book), eal.bound(book)["interactions"])
    return _L[k]


def one(key, name, N, W, H, r, S, knob, qdepth, keep=None, Sbuild=None, maxcycles=8_000_000, timeout=3000, claim=None):
    book, L, inter = loads(name, N)
    cs = placement.cells(W, H)
    Sb = Sbuild or S
    img = None
    if keep is None and Sb != S: keep = {c: S for c in cs}
    if keep is not None:
        img = fabric.Image(book, W, H, Sb, qdepth)
        from omega.ports import mk, ERA, NONE
        for c in cs:
            fnl = [s for s in range(Sb) if img.nodes[c][s] is None]
            fvl = [s for s in range(Sb) if img.vars[c][s] is None]
            for s in fnl[keep[c]:]:
                img.nodes[c][s] = [mk(ERA), mk(ERA)]; img.nown[c][s] = 14
            for s in fvl[keep[c]:]:
                img.vars[c][s] = mk(NONE); img.vown[c][s] = 14
    Lm = joint.margin(L, W, H)
    if keep is None:
        cert = joint.certified(W, H, L, S, qdepth, r=r)
    else:
        cert = (joint.certify_mesh(W, H, Lm, S=S, free_n=keep, free_v=keep, r=r) if W * H > 1 else max(Lm["W_nodes"], L["B_vars"]) <= min(keep.values())) \
            and joint.stack_ok(Lm, qdepth)
    claim = cert if claim is None else claim
    kn = dict(knob)
    extra = [f"+pcert={r or 1}", f"+rgrad={r or fabric.RGRAD}", f"+tcert={L['atoms']}"] + kn.pop("extra", [])
    t = time.time()
    res = rtl.run(book, W, H, slots=Sb, qdepth=qdepth, img=img, maxcycles=maxcycles, timeout=timeout, extra=extra, **kn)
    want = progs.expected(name, N)
    b0 = W * H * Sb - (sum(keep.values()) if keep else W * H * Sb)   # ballast slots (nodes and vars alike)
    ln, lv = res.get("pcert_used_n", 0) - b0, res.get("pcert_used_v", 0) - b0
    hull_ok = True
    for lam, p in Lm["hull"]:
        wn = int(lam * 8)
        pk = res.get(f"jcert_peak_{wn}")
        if pk is None: continue
        if F(pk - wn * b0 - 8 * b0, 8) > p: hull_ok = False
    rec = {"key": key, "prog": name, "N": N, "mesh": f"{W}x{H}", "rgrad": r, "S": S, "S_build": Sb, "qdepth": qdepth,
           "knob": knob, "claim": claim, "cert": cert, "L": (Lm["W_nodes"], L["B_vars"]), "Q": Lm["Q"], "atoms": L["atoms"],
           "status": res["status"],
           "ok": res["status"] == 0 and res["readback"] == want and res.get("interactions") == inter,
           "readback": str(res["readback"])[:40], "cycles": res.get("cycles"), "pcert_viol": res.get("pcert_viol"),
           "tcert_viol": res.get("tcert_viol"), "tcert_peak": res.get("tcert_peak"), "tcert_cell": res.get("tcert_cell"),
           "tcert_slack": res.get("tcert_slack"), "live_peak": (ln, lv), "hull_ok": hull_ok,
           "secs": round(time.time() - t, 1)}
    rec["sound"] = (not claim) or (rec["ok"] and rec["pcert_viol"] == 0 and rec["tcert_viol"] == 0 and ln <= Lm["W_nodes"]
                                   and lv <= L["B_vars"] and hull_ok and rec["tcert_peak"] <= Lm["Q"])
    return rec


def jobs_small():
    tab = json.load(open(os.path.join(OUT, "cert_table.json")))
    meshes = [("2x2", 2, 2, 3), ("3x3", 3, 3, 3), ("3x3 rgrad 4", 3, 3, 4), ("4x4 rgrad 6", 4, 4, 6)]
    for p in ["sum", "list", "higher", "fib", "treesum", "treesum_direct", "sort", "qsort_l"]:
        for mname, W, H, r in meshes:
            N = tab[p]["nmax"][f"{mname} S=1024"]
            for k, kn in enumerate(KNOBS[:4]):
                yield f"{p}({N}) {W}x{H} r{r} S1024 k{k}", dict(name=p, N=N, W=W, H=H, r=r, S=1024, knob=kn, qdepth=65536)


def jobs_hetero():
    W = H = 3
    cs = placement.cells(W, H)
    corner = {c: 8 for c in cs}; corner[(2, 2)] = 1024
    two = {c: 8 for c in cs}; two[(2, 0)] = 600; two[(0, 2)] = 600
    for tag, keep, name, N, r in (("corner", corner, "fib", 7, 4), ("corner", corner, "treesum", 4, 4), ("two", two, "sum", 60, 3),
                                  ("two", two, "list", 12, 3), ("corner", corner, "list", 12, 3), ("corner", corner, "fib", 7, 3)):
        for k, kn in enumerate(KNOBS[:4]):
            yield f"{tag} {name}({N}) r{r} k{k}", dict(name=name, N=N, W=W, H=H, r=r, S=1024, knob=kn, keep=keep, qdepth=65536)
    rnd = random.Random(30)
    progsN = [("fib", 6), ("fib", 8), ("treesum", 4), ("treesum", 5), ("treesum_direct", 6), ("sum", 40), ("list", 10), ("higher", 10), ("qsort_l", 4), ("sort", 5)]
    for i in range(40):
        keep = {c: (rnd.randint(4, 40) if rnd.random() < 0.6 else rnd.randint(64, 1024)) for c in cs}
        name, N = rnd.choice(progsN)
        r = rnd.choice((2, 3, 4))
        kn = dict(rnd.choice(KNOBS)); kn["seed"] = 200 + i
        yield f"rand{i} {name}({N}) r{r}", dict(name=name, N=N, W=W, H=H, r=r, S=1024, knob=kn, keep=keep, qdepth=65536)


def jobs_big():
    """Benchmark sizes on the smallest cell the joint certificate accepts (cells built at Sb, ballast leaves S free),
    QDEPTH 2^20 (>= Q + margin for every job here)."""
    bench = [("treesum_direct", 14), ("fib", 20), ("treesum", 9), ("list", 120), ("higher", 100), ("sum", 1000), ("fib", 19), ("treesum_direct", 13)]
    for W, H, r, Sb in ((2, 2, 3, 65536), (3, 3, 3, 65536), (4, 4, 6, 32768)):
        for name, N in bench:
            book, L, _ = loads(name, N)
            S = joint.min_slots(W, H, L, r=r)
            if S is None or S > Sb: continue
            for k, kn in enumerate(KNOBS):
                yield f"{name}({N}) {W}x{H} r{r} S{S} k{k}", dict(name=name, N=N, W=W, H=H, r=r, S=S, knob=kn, Sbuild=Sb, qdepth=1 << 20)


def jobs_boundary():
    """Uncertified configurations, to see whether the boundary means anything (claim False: no soundness requirement)."""
    cs3 = placement.cells(3, 3)
    # 1. stack: QDEPTH below the measured 1x1 depth-first need (the certificate wants Q + 3)
    for name, N, q in (("sum", 1000, 512), ("sum", 1000, 1024), ("list", 120, 64), ("fib", 12, 16), ("treesum", 7, 16)):
        for k, kn in enumerate(KNOBS[:2]):
            yield f"stack {name}({N}) 1x1 q{q} k{k}", dict(name=name, N=N, W=1, H=1, r=None, S=65536 if name == "sum" else 16384, knob=kn, qdepth=q, maxcycles=4_000_000)
    # 2. memory: enough slots in total, none roomy (every cell below lm_hi / below D_max)
    for free in (10, 20, 40):
        keep = {c: free for c in cs3}
        for name, N in (("fib", 6), ("treesum", 4), ("sum", 30)):
            for k, kn in enumerate(KNOBS[:2]):
                yield f"frag{free} {name}({N}) 3x3 k{k}", dict(name=name, N=N, W=3, H=3, r=3, S=1024, knob=kn, keep=keep, qdepth=65536, maxcycles=2_000_000)
    # 3. room too far: one rich corner, rgrad 2 (corner out of reach of the far corner)
    keep = {c: 8 for c in cs3}; keep[(2, 2)] = 1024
    for name, N in (("fib", 8), ("treesum", 5), ("list", 15)):
        for k, kn in enumerate(KNOBS[:3]):
            yield f"far {name}({N}) 3x3 r2 k{k}", dict(name=name, N=N, W=3, H=3, r=2, S=1024, knob=kn, keep=keep, qdepth=65536, maxcycles=2_000_000)


def main(which):
    path = os.path.join(OUT, f"val_{which}.jsonl")
    done = set()
    if os.path.exists(path):
        for line in open(path):
            try: done.add(json.loads(line)["key"])
            except Exception: pass
    gen = {"small": jobs_small, "hetero": jobs_hetero, "big": jobs_big, "boundary": jobs_boundary}[which]
    for key, kw in gen():
        if key in done: continue
        try:
            rec = one(key, **kw)
        except Exception as e:
            rec = {"key": key, "error": f"{type(e).__name__}: {e}"[:300], "sound": False, "claim": None}
        with open(path, "a") as f: f.write(json.dumps(rec) + "\n")
        print(json.dumps(rec), flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
