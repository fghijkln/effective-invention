"""Owner-capability isolation tests (SPEC 12): several mutually distrusting programs share one fabric.

Every case runs on the semantic model (golden), the cycle-level fabric model and the RTL.  Checked:
* every honest tenant's readback and live-node count equal the semantic model's (and, for the program
  demos, the program's known answer);
* the set of (trap reason, offending owner) pairs equals the semantic model's;
* the total interaction count equals the semantic model's.

usage: test_security.py [--fuzz K] [--no-rtl] [--quiet]
"""
import sys, os, random, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from omega import ir, semantic, fabric, progs, randnet
from omega.ports import *

SHAPES = [(1, 1), (2, 2), (4, 4), (3, 2)]


def build(parts):
    """parts: list of (owner, book).  Returns (merged book, tenants)."""
    book, mains = ir.merge_books([b for _, b in parts])
    return book, [{"owner": o, "main": m} for (o, _), m in zip(parts, mains)]


def attacker(src):
    return ir.parse_book(src)


def check(name, book, tenants, W, H, use_rtl=True, seed=1, jitter=0, stall=0, pmsg=128, scatter=None,
          fi=0, mut=0, want=None, honest=None, verbose=True):
    """want: optional list of expected readbacks per tenant (None = no expectation).
    honest: indices of tenants whose results must match (default: tenants that did not trap)."""
    ref = semantic.result_multi(book, tenants, seed=seed, geometry=(W, H, 1024))
    trapped = {o for _, o in ref["traps"]}
    honest = honest if honest is not None else [k for k, t in enumerate(tenants) if t["owner"] not in trapped]
    fails = []
    if want:
        for k, w in enumerate(want):
            if w is not None and ref["tenants"][k]["readback"] != w:
                fails.append(f"semantic tenant {k}: {ref['tenants'][k]['readback']} want {w}")

    def cmp(tag, per, traps, inter):
        for k in honest:
            if (per[k]["readback"], per[k]["nodes"]) != (ref["tenants"][k]["readback"], ref["tenants"][k]["nodes"]):
                fails.append(f"{tag} tenant {k} (owner {tenants[k]['owner']}): {per[k]['readback'][:60]}/{per[k]['nodes']} "
                             f"want {ref['tenants'][k]['readback'][:60]}/{ref['tenants'][k]['nodes']}")
        if fi:
            # sender-side checks skipped: a later check (receiver T1, or the slot-tag check T2) must still
            # catch every corrupted access; T2 may report a re-stamped port as a forged tag
            okr = {r for r, _ in ref["traps"]} | ({TRAP_FORGED} if any(r == TRAP_CROSS for r, _ in ref["traps"]) else set())
            if bool(traps) != bool(ref["traps"]) or any(r not in okr for r, _ in traps):
                fails.append(f"{tag} traps {traps} want {ref['traps']} (fault injection)")
        elif traps != ref["traps"]:
            fails.append(f"{tag} traps {traps} want {ref['traps']}")
        if inter != ref["interactions"] and not fi:   # under fault injection a skipped sender check may count one REF expansion
            fails.append(f"{tag} interactions {inter} want {ref['interactions']}")
    ll = int(seed % 3 != 0)       # step 12: link orientation varies with the seed (both paths checked)
    if mut == 0:
        img = fabric.Image(book, W, H, 1024, 1024, scatter=scatter, tenants=tenants)
        f = fabric.Fabric(book, W, H, seed=seed, p_jitter=jitter / 256, p_stall=stall / 256, img=img,
                          fi_nosend=bool(fi & 1), link_local=ll).run()
        cmp(f"fabric {W}x{H}", f.tenant_results(), f.traps(), f.interactions)
    r = None
    if use_rtl:
        from omega import rtl
        img = fabric.Image(book, W, H, 1024, 1024, scatter=scatter, tenants=tenants)
        r = rtl.run(book, W, H, img=img, seed=seed, jitter=jitter, stall=stall, pmsg=pmsg, fi=fi, mut=mut,
                    maxcycles=2_000_000, timeout=120, link_local=ll)
        if r["status"] != 0:
            fails.append(f"rtl {W}x{H} status {r['status']}")
        else:
            cmp(f"rtl {W}x{H}", r["tenants"], r["traps"], r["interactions"])
    if fails and verbose:
        print(f"FAIL {name} {W}x{H} seed={seed} fi={fi}: " + "; ".join(fails[:4]))
    return not fails, ref, r


# --------------------------------------------------------------------------------------------- cases
def demo_cases():
    """Two (and four) mutually distrusting programs on one fabric, each with its known answer."""
    out = []
    b, t = build([(1, progs.book("fib", 12)), (2, progs.book("qsort", 15))])
    out.append(("demo fib(12) || qsort(15)", b, t, [progs.expected("fib", 12), progs.expected("qsort", 15)]))
    b, t = build([(3, progs.book("treesum", 6)), (5, progs.book("list", 20)), (7, progs.book("sort", 10)),
                  (0, progs.book("higher", 7))])
    out.append(("demo 4 tenants", b, t, [progs.expected("treesum", 6), progs.expected("list", 20),
                                         progs.expected("sort", 10), progs.expected("higher", 7)]))
    return out


ATTACKS = [
    # name, attacker IR (victim is tenant 0 = fib(10), owner 1; attacker is tenant 1, owner 9), expected trap reasons
    ("steal-result: write a forged result into the victim's root var",
     "@main = r & #7 ~ r & !var(0,0,0) ~ #666", {TRAP_FORGED}),
    ("read-result: link a forged root-var pointer with a CON to capture the value",
     "@main = r & #7 ~ r & !var(0,0,0) ~ (a a)", {TRAP_FORGED}),
    ("out-of-bounds slot", "@main = r & #7 ~ r & !var(0,0,4000) ~ #1", {TRAP_OOB}),
    ("out-of-bounds cell", "@main = r & #7 ~ r & !var(15,15,3) ~ #1", {TRAP_OOB}),
    ("forged node pointer outside the fabric", "@main = r & #7 ~ r & * ~ !con(9,0,1)", {TRAP_OOB}),
    ("forged node pointer meets a real node", "@main = r & (x x) ~ !dup(0,9,1) & #3 ~ r", {TRAP_OOB}),
    ("attack inside a lazily expanded definition",
     "@spy = (x x) & !var(0,0,0) ~ #9\n@main = r & @spy ~ (#5 r)", {TRAP_FORGED}),
]


# victim whose result is a pair node loaded at cell (0,0) node slot 0 and never consumed, so a forged
# in-bounds node pointer to it is deterministic: it always names a slot tagged with the victim's owner
NODE_ATTACKS = [
    ("erase the victim's result node", "@main = r & #7 ~ r & * ~ !con(0,0,0)", {TRAP_FORGED}),
    ("annihilate with the victim's result node to read its fields",
     "@main = (a b) & (a b) ~ !con(0,0,0)", {TRAP_FORGED}),
    ("duplicate the victim's result node", "@main = (a b) & {3 a b} ~ !con(0,0,0)", {TRAP_FORGED}),
]


def attack_cases():
    out = []
    for name, src, reasons in ATTACKS:
        b, t = build([(1, progs.book("fib", 10)), (9, attacker(src))])
        out.append((f"attack {name}", b, t, [progs.expected("fib", 10), None], reasons))
    for name, src, reasons in NODE_ATTACKS:
        b, t = build([(2, ir.parse_book("@main = (#1 #2)")), (9, attacker(src))])
        out.append((f"attack {name}", b, t, ["(#1 #2)", None], reasons))
    return out


def cross_patch(victim_owner):
    """Fault injection (a corrupted loader/DMA, not something a program can express): the attacker's
    first initial link gets one port re-stamped with the victim's owner id."""
    def patch(links):
        a, b = links[-1]
        return links[:-1] + [(with_owner(a, victim_owner), b)]
    return patch


def cross_cases():
    out = []
    for src in ["@main = r & #7 ~ r & (x x) ~ (y y)", "@main = r & #7 ~ r & a ~ (a *)",
                "@f = (a a)\n@main = r & #7 ~ r & @f ~ (b b)"]:
        b, t = build([(1, progs.book("fib", 9)), (9, attacker(src))])
        t[1]["patch"] = cross_patch(1)
        out.append((f"cross-owner fault injection {src.splitlines()[-1]}", b, t, [progs.expected("fib", 9), None], {TRAP_CROSS}))
    return out


# --------------------------------------------------------------------------------------------- fuzz
def fuzz_case(i):
    """2-4 random tenants with random owners; with probability 1/2 one of them is an attacker whose
    book carries extra forged redexes (victim root vars, out-of-bounds vars / nodes)."""
    rng = random.Random(i * 104729 + 7)
    n = rng.randint(2, 4)
    owners = rng.sample(range(15), n)
    books, k = [], 0
    while len(books) < n:
        b = randnet.gen_book(i * 31 + k); k += 1
        try:
            semantic.result(b, fuel=4000)
        except semantic.OutOfFuel:
            continue
        books.append(b)
    att = rng.randrange(n) if rng.random() < 0.5 else None
    if att is not None:
        txt = books[att].to_text()
        extra = []
        for _ in range(rng.randint(1, 2)):
            kind = rng.randrange(4)
            victim = rng.choice([j for j in range(n) if j != att])
            if kind == 0: extra.append(f"& !var(0,0,{victim}) ~ #{rng.randint(0, 99)}")
            elif kind == 1: extra.append(f"& !var(0,0,{rng.randint(1100, 4000)}) ~ *")
            elif kind == 2: extra.append(f"& !var(15,{rng.randint(0, 15)},1) ~ #1")
            else: extra.append(f"& * ~ !con(12,{rng.randint(0, 15)},{rng.randint(0, 99)})")
        lines = txt.strip().split("\n")
        # append to @main (first definition)
        mi = next(j for j, l in enumerate(lines) if l.startswith("@main"))
        lines.insert(mi + 1, "  " + " ".join(extra))
        books[att] = ir.parse_book("\n".join(lines))
    book, tenants = build(list(zip(owners, books)))
    try:
        semantic.result_multi(book, tenants, fuel=20000)
    except semantic.OutOfFuel:
        return None
    W, H = SHAPES[i % len(SHAPES)]
    knobs = dict(seed=rng.randint(1, 2**31), jitter=rng.choice([0, 30, 80]), stall=rng.choice([0, 20]),
                 pmsg=rng.randint(0, 255), scatter=rng.randint(0, 10**9) if rng.random() < 0.6 else None,
                 fi=rng.choice([0, 0, 1]))
    return book, tenants, W, H, knobs, att


def main():
    use_rtl = "--no-rtl" not in sys.argv
    fuzz = int(sys.argv[sys.argv.index("--fuzz") + 1]) if "--fuzz" in sys.argv else 0
    t0 = time.time()
    n = fails = 0
    for name, b, t, want in demo_cases():
        for (W, H) in SHAPES:
            for k, kn in enumerate([dict(), dict(jitter=60, stall=30, pmsg=40, scatter=7)]):
                n += 1
                ok, ref, _ = check(name, b, t, W, H, use_rtl, seed=W * 10 + H + k, want=want, **kn)
                if ok and ref["traps"]:
                    ok = False; print(f"FAIL {name}: unexpected traps {ref['traps']}")
                fails += not ok
    for name, b, t, want, reasons in attack_cases() + cross_cases():
        for (W, H) in SHAPES:
            for fi in (0, 1):
                n += 1
                ok, ref, r = check(name, b, t, W, H, use_rtl, seed=W + 3 * H + fi, jitter=40 * fi,
                                   scatter=(5 if fi and "result node" not in name else None), fi=fi, want=want, honest=[0])
                got = {rs for rs, o in ref["traps"]}
                if got != reasons or (TRAP_CROSS not in reasons and any(o != t[1]["owner"] for _, o in ref["traps"])):
                    ok = False; print(f"FAIL {name}: semantic traps {ref['traps']} want reasons {reasons}")
                fails += not ok
    nf = rej = 0
    i = 0
    while nf < fuzz:
        c = fuzz_case(i); i += 1
        if c is None:
            rej += 1; continue
        book, tenants, W, H, kn, att = c
        nf += 1; n += 1
        ok, ref, _ = check(f"mt-fuzz {i - 1} (attacker={att})", book, tenants, W, H, use_rtl, **kn)
        if ok and att is None and ref["traps"]:
            ok = False; print(f"FAIL mt-fuzz {i - 1}: honest tenants trapped {ref['traps']}")
        fails += not ok
    print(f"security tests: {n - fails}/{n} pass ({fuzz} multi-tenant fuzz, {rej} rejected) "
          f"[{'semantic + fabric + RTL' if use_rtl else 'semantic + fabric'}] {time.time() - t0:.0f}s")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
