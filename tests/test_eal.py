"""Step 24: Ω-L (light-affine subset, omega/eal.py) checker and compile-time peak-memory bound.

Sections
* checker units: programs that must be accepted / rejected (and with which rule);
* census: which programs of the suite (programs/*.olm) and of the unit-test language cases are in Ω-L;
* bound: schedule independence (depth first, breadth first, random orders give the same B), an independent
  recount of B, and peak <= B on the semantic reducer (5 orders), the fabric model (1x1 / 2x2 / 4x4) and the
  RTL (1x1 default cell; per-cell peaks on 2x2);
* RTL at the bound: one 4096-slot cell with ballast leaving exactly B_nodes - n0 free node slots and
  B_vars - v0 free var slots (so the program has B node / var slots), and a 2x2 mesh whose every cell keeps
  slots_mesh free: must finish with the right answer (no status-3 stall);
* typed fuzz: random Ω-L programs (producers, transformers, consumers, closures, numeric recursions) and
  random programs that break one rule (must be rejected).
* --mutants: the checker / bound mutants of omega/eal.py (OMEGA_EAL_MUT) must each make this suite fail.

usage: test_eal.py [--no-rtl] [--fuzz K] [--rtl-fuzz K] [--mutants] [--json FILE]
"""
import sys, os, random, time, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
from omega import eal, lang, semantic, fabric, progs
from omega.ports import *

LIST = "data List = Nil | Cons(h, t)\n"
TREE = "data Tree = Leaf(v) | Node(l, r)\n"
ACCEPT = [
    ("sum_switch", "def s(n) = switch n { 0 => 0; p => n + s(p) }\ndef main = s(10)"),
    ("guarded_minus2", "def f(n) = if n < 2 then n else f(n - 1) + f(n - 2)\ndef main = f(9)"),
    ("guard_eq0", "def f(n) = if n == 0 then 7 else f(n - 1) * 2\ndef main = f(5)"),
    ("pred_minus", "def f(n) = switch n { 0 => 1; p => if p < 3 then p else f(p - 2) + 1 }\ndef main = f(11)"),
    ("num_dup", "def sq(x) = x * x + x\ndef main = sq(sq(3))"),
    ("accumulator", "def f(n, a) = switch n { 0 => a; p => f(p, a * 3 + 1) }\ndef main = f(12, 1)"),
    ("mutual", "def ev(n) = switch n { 0 => 1; p => od(p) }\ndef od(n) = switch n { 0 => 0; p => ev(p) }\ndef main = ev(9)"),
    ("nested_pattern", LIST + "def pairs(xs) = match xs { Cons(a, Cons(b, t)) => a * b + pairs(t); _ => 0 }\n"
     "def mk(n) = switch n { 0 => Nil; p => Cons(n, mk(p)) }\ndef main = pairs(mk(7))"),
    ("map_bang", LIST + "def map(f, xs) = match xs { Nil => Nil; Cons(h, t) => Cons(f(h), map(f, t)) }\n"
     "def len(xs) = match xs { Nil => 0; Cons(h, t) => h + len(t) }\ndef main = len(map(\\x -> x * x, Cons(2, Cons(3, Nil))))"),
    ("bang_global", LIST + "def inc(x) = x + 1\ndef map(f, xs) = match xs { Nil => Nil; Cons(h, t) => Cons(f(h), map(f, t)) }\n"
     "def len(xs) = match xs { Nil => 0; Cons(h, t) => h + len(t) }\ndef main = len(map(inc, Cons(2, Cons(3, Nil))))"),
    ("bang_capture_num", LIST + "def map(f, xs) = match xs { Nil => Nil; Cons(h, t) => Cons(f(h), map(f, t)) }\n"
     "def len(xs) = match xs { Nil => 0; Cons(h, t) => h + len(t) }\ndef g(k) = len(map(\\x -> x + k, Cons(2, Cons(3, Nil))))\ndef main = g(5)"),
    ("tree", TREE + "def gen(d) = switch d { 0 => Leaf(1); p => Node(gen(p), gen(p)) }\n"
     "def mir(t) = match t { Leaf(v) => Leaf(v); Node(l, r) => Node(mir(r), mir(l)) }\n"
     "def tsum(t) = match t { Leaf(v) => v; Node(l, r) => tsum(l) + tsum(r) }\ndef main = tsum(mir(gen(4)))"),
    ("reverse_acc", LIST + "def rev(xs, a) = match xs { Nil => a; Cons(h, t) => rev(t, Cons(h, a)) }\n"
     "def chk(xs, i) = match xs { Nil => 0; Cons(h, t) => i * h + chk(t, i + 1) }\n"
     "def mk(n) = switch n { 0 => Nil; p => Cons(n, mk(p)) }\ndef main = chk(rev(mk(6), Nil), 1)"),
    ("compose", "def compose(f, g) = \\x -> f(g(x))\ndef twice(f) = compose(f, f)\ndef main = twice(\\x -> x * 3)(5)"),
    ("erase_data", LIST + "def k(xs, n) = n + 1\ndef main = k(Cons(1, Nil), 4)"),
]
REJECT = [
    ("dup_list", LIST + "data P = P(a, b)\ndef d(xs) = P(xs, xs)\ndef main = match d(Cons(1, Nil)) { P(a, b) => 0 }", "affine"),
    ("dup_list_app", LIST + "def app(xs, ys) = match xs { Nil => ys; Cons(h, t) => Cons(h, app(t, ys)) }\n"
     "def len(xs) = match xs { Nil => 0; Cons(h, t) => 1 + len(t) }\ndef dbl(xs) = app(xs, xs)\ndef main = len(dbl(Cons(1, Nil)))", "affine"),
    ("no_decrease", "def f(n) = switch n { 0 => 0; p => f(n) }\ndef main = f(3)", "recursion"),
    ("increase", "def f(n) = if n > 100 then n else f(n + 1)\ndef main = f(3)", "recursion"),
    ("unguarded_minus", "def f(n) = if n < 1 then 0 else f(n - 2)\ndef main = f(6)", "recursion"),
    ("no_guard", "def f(n) = f(n - 1)\ndef main = f(6)", "recursion"),
    ("loop0", "def loop = loop\ndef main = loop", "recursion"),
    ("rec_value", "def ap(g, n) = g(n)\ndef f(n) = switch n { 0 => 0; p => ap(f, p) }\ndef main = f(3)", "recursion"),
    ("ackermann", "def ack(m, n) = switch m { 0 => n + 1; p => switch n { 0 => ack(p, 1); q => ack(p, ack(m, q)) } }\ndef main = ack(2, 2)", "recursion"),
    ("fun_in_data", "data Box = B(f)\ndef unbox(b) = match b { B(f) => f }\ndef w(x) = unbox(x)(x)\ndef main = w(B(w))", "type"),
    ("field_types", "data B = B(x)\ndef get(b) = match b { B(v) => v }\ndef main = get(B(1)) + get(get(B(B(2))))", "type"),
    ("bang_nonInert", LIST + "def fib(n) = if n < 2 then n else fib(n - 1) + fib(n - 2)\n"
     "def map(f, xs) = match xs { Nil => Nil; Cons(h, t) => Cons(f(h), map(f, t)) }\n"
     "def len(xs) = match xs { Nil => 0; Cons(h, t) => h + len(t) }\ndef main = len(map(\\x -> fib(x), Cons(2, Nil)))", "bang"),
    ("bang_closure_app", "def compose(f, g) = \\x -> f(g(x))\ndef twice(f) = compose(f, f)\n"
     "def main = twice(compose(\\x -> x + 1, \\x -> x * 2))(1)", "bang"),
    ("bang_let", "def main = let g = \\x -> x + 1 in g(g(1))", "bang"),
    ("bang_partial", "def twice(f, x) = f(f(x))\ndef main = twice(twice(\\x -> x + 1), 0)", "bang"),
    ("inline_arms_share", LIST + "def pick(b, ys) = switch b { 0 => ys; _ => ys }\n"
     "def len(xs) = match xs { Nil => 0; Cons(h, t) => 1 + len(t) }\ndef main = len(pick(1, Cons(1, Nil)))", "affine"),
    ("dup_poly", "data P = P(a, b)\ndef d(x) = P(x, x)\ndef main = 3", "affine"),
]


def census():
    """(name, in Ω-L, reason) for every program of the suite and every unit-test language case."""
    import test_units
    out = []
    for name in sorted(progs.REF):
        r = eal.check(progs.source(name, 5))
        out.append((f"programs/{name}.olm", r["ok"], r.get("reason", "")))
    for name, src, _ in test_units.LANG:
        r = eal.check(src)
        out.append((f"test_units.LANG/{name}", r["ok"], r.get("reason", "")))
    return out


CENSUS_WANT = {"programs/qsort.olm": False, "test_units.LANG/church": False, "test_units.LANG/ackermann": False,
               "test_units.LANG/default_and_binder": False, "test_units.LANG/pair_columns": False,
               "test_units.LANG/polymorphic_helper": False}


# ------------------------------------------------------------------------------------------------ bound
class Recount(semantic.Net):
    """Independent recount of B (does not share code with eal.CountNet)."""
    def __init__(self, *a, **k):
        super().__init__(*a, **k); self.allocs = 0; self.ups = 0

    def alloc_var(self, o=0):
        self.allocs += 1; return super().alloc_var(o)

    def normalize(self, seed=None, fuel=10**8, order="random"):
        while self.rdx:
            a, b = self.rdx.pop()
            before = len(self.nodes)
            self.interact(a, b)
            self.ups += max(0, len(self.nodes) - before)


def recount(book):
    net = Recount(book); root = net.alloc_var()
    net.instantiate(book.id("main"), mk(VAR, 0, root))
    n0 = len(net.nodes)
    net.normalize()
    return n0 + net.ups, net.allocs


def sem_peaks(book):
    """Peak nodes / vars over 5 reduction orders, and the bound from each."""
    rs = [eal.count_run(book, "lifo"), eal.count_run(book, "fifo")] + [eal.count_run(book, "random", s) for s in (1, 2, 3)]
    return rs


def fabric_peak(book, W, H, seed, slots=2048):
    f = fabric.Fabric(book, W, H, slots=slots, seed=seed, p_jitter=0.1 if W * H > 1 else 0.0,
                      img=fabric.Image(book, W, H, slots, 1024, scatter=seed if W * H > 1 else None))
    pk = {"g_nodes": 0, "g_vars": 0, "c_nodes": 0, "c_vars": 0}
    step0 = f.step

    def step():
        step0()
        gn = gv = 0
        for c in f.cells.values():
            un, uv = slots - len(c.nfree), slots - len(c.vfree)
            gn += un; gv += uv
            if un > pk["c_nodes"]: pk["c_nodes"] = un
            if uv > pk["c_vars"]: pk["c_vars"] = uv
        if gn > pk["g_nodes"]: pk["g_nodes"] = gn
        if gv > pk["g_vars"]: pk["g_vars"] = gv
    f.step = step
    f.run()
    pk["readback"] = f.readback(); pk["interactions"] = f.interactions; pk["cycles"] = f.cycles
    return pk


def ballast(book, W, H, slots, keep_n, keep_v):
    import test_mempress as tm
    return tm.ballast_img(book, W, H, slots, keep_n, keep_v, cells=[(x, y) for x in range(W) for y in range(H)])


def rtl_at_bound(book, b, want, seed=3, slots=4096):
    """One cell with exactly B node / var slots for the program.  Returns (ok, live peak nodes, live peak vars, cycles)."""
    from omega import rtl
    kn, kv = b["B_nodes"] - b["n0"], b["B_vars"] - b["v0"]
    r = rtl.run(book, 1, 1, slots=slots, img=ballast(book, 1, 1, slots, kn, kv), seed=seed, maxcycles=4_000_000)
    c = r["cells"][(0, 0)]
    pn = c["peak_nodes"] - (slots - kn - b["n0"]); pv = c["peak_vars"] - (slots - kv - b["v0"])
    return r["status"] == 0 and r["readback"] == want, pn, pv, r.get("cycles"), r["status"]


def rtl_mesh_at_bound(book, b, want, W=2, H=2, seed=5, slots=4096):
    from omega import rtl
    k = b["slots_mesh"]
    r = rtl.run(book, W, H, slots=slots, img=ballast(book, W, H, slots, k, k), seed=seed, jitter=30, maxcycles=4_000_000)
    return r["status"] == 0 and r["readback"] == want, r["status"]


# ------------------------------------------------------------------------------------------- typed fuzz
LAMS1 = ["\\x -> x * x + 1", "\\x -> x + {k}", "\\x -> (x ^ {k}) & 255", "\\x -> x * {k} % 97", "\\x -> x - x / 2"]
LAMS2 = ["\\a b -> a + b", "\\a b -> a * {k} + b", "\\a b -> (a ^ b) + 1", "\\a b -> b * 2 + a % 7"]
EXPRS = ["s % {k}", "s * {k} + 1", "(s ^ {k}) & 63", "s + n", "n * {k}"]


def gen_program(rng):
    """A random Ω-L program: returns (source, list of building blocks)."""
    k = lambda: rng.randint(1, 9)
    defs, used = [], []
    defs.append(LIST); defs.append(TREE)
    e = rng.choice(EXPRS).format(k=k())
    defs.append(f"def gen(n, s) = switch n {{ 0 => Nil; p => Cons({e}, gen(p, (s * {k()} + {k()}) % 1000)) }}")
    defs.append(f"def tgen(d, s) = switch d {{ 0 => Leaf(s % {k() + 3}); p => Node(tgen(p, s + {k()}), tgen(p, s * 2 + 1)) }}")
    defs.append("def map(f, xs) = match xs { Nil => Nil; Cons(h, t) => Cons(f(h), map(f, t)) }")
    defs.append(f"def filt(xs) = match xs {{ Nil => Nil; Cons(h, t) => if h % {rng.randint(2, 4)} == 0 then Cons(h, filt(t)) else filt(t) }}")
    defs.append("def app(xs, ys) = match xs { Nil => ys; Cons(h, t) => Cons(h, app(t, ys)) }")
    defs.append("def ins(x, xs) = match xs { Nil => Cons(x, Nil); Cons(h, t) => if x <= h then Cons(x, Cons(h, t)) else Cons(h, ins(x, t)) }")
    defs.append("def isort(xs) = match xs { Nil => Nil; Cons(h, t) => ins(h, isort(t)) }")
    defs.append("def rev(xs, a) = match xs { Nil => a; Cons(h, t) => rev(t, Cons(h, a)) }")
    defs.append("def foldr(f, z, xs) = match xs { Nil => z; Cons(h, t) => f(h, foldr(f, z, t)) }")
    defs.append("def chk(xs, i) = match xs { Nil => 0; Cons(h, t) => i * h + chk(t, i + 1) }")
    defs.append("def tsum(t) = match t { Leaf(v) => v; Node(l, r) => tsum(l) + tsum(r) }")
    defs.append("def tmap(f, t) = match t { Leaf(v) => Leaf(f(v)); Node(l, r) => Node(tmap(f, l), tmap(f, r)) }")
    defs.append("def mir(t) = match t { Leaf(v) => Leaf(v); Node(l, r) => Node(mir(r), mir(l)) }")
    defs.append("def tflat(t, a) = match t { Leaf(v) => Cons(v, a); Node(l, r) => tflat(l, tflat(r, a)) }")
    c = rng.randint(2, 3)
    defs.append(f"def nrec(n, a) = if n < {c} then a + n else nrec(n - 1, a + 1) {rng.choice(['+', '^', '*'])} nrec(n - {c}, a)")
    defs.append(f"def nlin(n, a) = switch n {{ 0 => a; p => nlin(p, (a * {k()} + n) % 65536) }}")
    defs.append("def compose(f, g) = \\x -> f(g(x))")
    defs.append("def twice(f) = compose(f, f)")

    def lst(depth):
        r = rng.random()
        if depth <= 0 or r < 0.3:
            used.append("gen"); return f"gen({rng.randint(0, 9)}, {rng.randint(0, 99)})"
        if r < 0.45: used.append("map"); return f"map({rng.choice(LAMS1).format(k=k())}, {lst(depth - 1)})"
        if r < 0.55: used.append("filt"); return f"filt({lst(depth - 1)})"
        if r < 0.65: used.append("app"); return f"app({lst(depth - 1)}, {lst(depth - 2)})"
        if r < 0.78: used.append("isort"); return f"isort({lst(depth - 1)})"
        if r < 0.88: used.append("rev"); return f"rev({lst(depth - 1)}, Nil)"
        used.append("tflat"); return f"tflat({tree(depth - 1)}, Nil)"

    def tree(depth):
        r = rng.random()
        if depth <= 0 or r < 0.5:
            used.append("tgen"); return f"tgen({rng.randint(0, 4)}, {rng.randint(0, 50)})"
        if r < 0.75: used.append("tmap"); return f"tmap({rng.choice(LAMS1).format(k=k())}, {tree(depth - 1)})"
        used.append("mir"); return f"mir({tree(depth - 1)})"

    def num(depth):
        r = rng.random()
        if depth <= 0 or r < 0.15: return str(rng.randint(0, 50))
        if r < 0.3: used.append("chk"); return f"chk({lst(depth - 1)}, 1)"
        if r < 0.45: used.append("foldr"); return f"foldr({rng.choice(LAMS2).format(k=k())}, {num(0)}, {lst(depth - 1)})"
        if r < 0.58: used.append("tsum"); return f"tsum({tree(depth - 1)})"
        if r < 0.68: used.append("nrec"); return f"nrec({rng.randint(0, 9)}, {num(0)})"
        if r < 0.78: used.append("nlin"); return f"nlin({rng.randint(0, 30)}, {num(depth - 1)})"
        if r < 0.88: used.append("twice"); return f"twice({rng.choice(LAMS1).format(k=k())})({num(depth - 1)})"
        return f"({num(depth - 1)} {rng.choice(['+', '*', '^', '-'])} {num(depth - 1)})"
    main = num(3)
    return "\n".join(defs) + f"\ndef main = {main}\n", sorted(set(used))


BREAK = [  # (rule, transformation of a good program): each must be rejected
    ("affine", lambda s: s.replace("def app(xs, ys) =", "def dbl(xs) = app(xs, xs)\ndef app(xs, ys) =") + "def zz = chk(dbl(gen(3, 1)), 1)\n"),
    ("recursion", lambda s: s.replace("filt(t) }", "filt(Cons(h, t)) }")),
    ("recursion", lambda s: s.replace("nlin(p,", "nlin(n,")),
    ("recursion", lambda s: s.replace("nrec(n - 1,", "nrec(n + 1,")),
    ("bang", lambda s: s + "def zz = chk(map(\\x -> nlin(x, 1), gen(3, 2)), 1)\n"),
    ("type", lambda s: s + "def zz = tsum(Leaf(\\x -> x))\n"),
]


def fuzz(K, rtl_k=0, seed=2024, verbose=True, log=None):
    rng = random.Random(seed)
    n = fails = acc = brk = rtl_n = 0
    ratios = []
    for i in range(K):
        src, used = gen_program(rng)
        rep = eal.check(src)
        n += 1
        if not rep["ok"]:
            fails += 1; verbose and print(f"FAIL fuzz {i}: rejected a typed program: {rep['reason']}"); continue
        acc += 1
        book = lang.compile_book(src)
        try:
            rs = sem_peaks(book)
        except semantic.OutOfFuel:
            fails += 1; verbose and print(f"FAIL fuzz {i}: out of fuel"); continue
        b = eal.bound(book)
        want = rs[0]["readback"]
        bad = [r for r in rs if (r["B_nodes"], r["B_vars"]) != (b["B_nodes"], b["B_vars"]) or r["readback"] != want
               or r["peak_nodes"] > b["B_nodes"] or r["peak_vars"] > b["B_vars"]]
        if bad or recount(book) != (b["B_nodes"], b["B_vars"]):
            fails += 1; verbose and print(f"FAIL fuzz {i}: bound {b['B_nodes']}/{b['B_vars']} vs {[(r['B_nodes'], r['peak_nodes'], r['peak_vars']) for r in rs]}"); continue
        W, H = rng.choice([(1, 1), (2, 2), (3, 2), (4, 4)])
        pk = fabric_peak(book, W, H, seed=rng.randint(1, 10**6))
        if pk["readback"] != want or max(pk["g_nodes"], pk["c_nodes"]) > b["B_nodes"] or max(pk["g_vars"], pk["c_vars"]) > b["B_vars"]:
            fails += 1; verbose and print(f"FAIL fuzz {i}: fabric {W}x{H} peak {pk} > bound {b['B_nodes']}/{b['B_vars']}"); continue
        if b["B_nodes"] and b["B_vars"]: ratios.append((b["B_nodes"] / max(1, max(r["peak_nodes"] for r in rs)), b["B_vars"] / max(1, max(r["peak_vars"] for r in rs))))
        rec = {"i": i, "used": used, "B": [b["B_nodes"], b["B_vars"]], "sem_peak": [max(r["peak_nodes"] for r in rs), max(r["peak_vars"] for r in rs)],
               "fab": [W, H, pk["g_nodes"], pk["g_vars"]], "inter": b["interactions"]}
        if rtl_n < rtl_k and b["slots_1x1"] <= 3800:
            rtl_n += 1; n += 1
            ok, pn, pv, cyc, st = rtl_at_bound(book, b, want, seed=rng.randint(1, 10**6))
            rec["rtl"] = [pn, pv, cyc, st]
            if not ok or pn > b["B_nodes"] or pv > b["B_vars"]:
                fails += 1; verbose and print(f"FAIL fuzz {i}: RTL 1x1 at the bound: status {st}, peak {pn}/{pv} vs {b['B_nodes']}/{b['B_vars']}")
        if log: log.write(json.dumps(rec) + "\n"); log.flush()
        # the same program with one rule broken must be rejected
        rule, f = BREAK[i % len(BREAK)]
        bsrc = f(src)
        n += 1; brk += 1
        r2 = eal.check(bsrc)
        if r2["ok"] or not r2["reason"].startswith(rule):
            fails += 1; verbose and print(f"FAIL fuzz {i}: broken ({rule}) program: {r2.get('reason', 'accepted')}")
    if verbose and ratios:
        rn = sorted(x for x, _ in ratios); rv = sorted(y for _, y in ratios)
        print(f"  fuzz: {acc} typed programs, {brk} broken ones, {rtl_n} on the RTL; B / semantic peak: nodes median {rn[len(rn) // 2]:.1f} "
              f"(min {rn[0]:.1f}, max {rn[-1]:.1f}), vars median {rv[len(rv) // 2]:.1f} (min {rv[0]:.1f}, max {rv[-1]:.1f})")
    return n, fails


# ------------------------------------------------------------------------------------------------ suite
SUITE = [("fib", [6, 10, 12]), ("sum", [0, 30, 100]), ("fact", [12]), ("list", [0, 10, 25]), ("treesum", [0, 3, 5, 7]),
         ("treesum_direct", [5, 9]), ("sort", [0, 8, 15]), ("higher", [0, 9, 30])]
RTL_AT = [("fib", 10), ("sum", 100), ("fact", 12), ("list", 25), ("treesum", 6), ("treesum_direct", 8), ("sort", 15), ("higher", 30)]
MESH_AT = [("fib", 8), ("list", 20), ("treesum", 5), ("sort", 10), ("higher", 30)]


def run(use_rtl=True, fuzz_k=0, rtl_fuzz=0, verbose=True, out=None):
    n = fails = 0
    t0 = time.time()
    rows = []

    def fail(msg):
        nonlocal fails
        fails += 1
        if verbose: print("FAIL", msg)
    for name, src in ACCEPT:
        n += 1
        r = eal.check(src)
        if not r["ok"]: fail(f"accept {name}: {r['reason']}"); continue
        b = lang.compile_book(src)
        if semantic.result(b)["readback"] != eal.count_run(b)["readback"]: fail(f"accept {name}: counting run result")
    for name, src, rule in REJECT:
        n += 1
        r = eal.check(src)
        if r["ok"] or not r["reason"].startswith(rule): fail(f"reject {name}: {r.get('reason', 'accepted')} (want {rule})")
    cen = census()
    for name, ok, why in cen:
        n += 1
        if ok != CENSUS_WANT.get(name, True): fail(f"census {name}: {ok} {why}")
    if verbose:
        print(f"  census: {sum(ok for _, ok, _ in cen)}/{len(cen)} in Ω-L; rejected: " + "; ".join(f"{nm.split('/')[-1]} ({w.split(':')[0]})" for nm, ok, w in cen if not ok))
    # bound: schedule independence, recount, semantic peaks, fabric peaks
    for name, Ns in SUITE:
        for N in Ns:
            book = progs.book(name, N); want = progs.expected(name, N)
            b = eal.bound(book); rs = sem_peaks(book)
            n += 1
            if any((r["B_nodes"], r["B_vars"]) != (b["B_nodes"], b["B_vars"]) or r["readback"] != want for r in rs):
                fail(f"bound {name}({N}) depends on the order: {[(r['B_nodes'], r['B_vars']) for r in rs]}")
            n += 1
            if recount(book) != (b["B_nodes"], b["B_vars"]): fail(f"bound {name}({N}): recount {recount(book)} != {b['B_nodes']}, {b['B_vars']}")
            n += 1
            pn, pv = max(r["peak_nodes"] for r in rs), max(r["peak_vars"] for r in rs)
            if pn > b["B_nodes"] or pv > b["B_vars"]: fail(f"bound {name}({N}): semantic peak {pn}/{pv} > {b['B_nodes']}/{b['B_vars']}")
            row = {"prog": name, "N": N, "B_nodes": b["B_nodes"], "B_vars": b["B_vars"], "lifo": [rs[0]["peak_nodes"], rs[0]["peak_vars"]],
                   "fifo": [rs[1]["peak_nodes"], rs[1]["peak_vars"]], "random": [max(r["peak_nodes"] for r in rs[2:]), max(r["peak_vars"] for r in rs[2:])],
                   "slots_mesh": b["slots_mesh"], "interactions": b["interactions"]}
            if N == Ns[-1]:
                for W, H, s in ((1, 1, 0), (2, 2, 7), (4, 4, 9)):
                    n += 1
                    pk = fabric_peak(book, W, H, s)
                    row[f"fabric_{W}x{H}"] = [pk["g_nodes"], pk["g_vars"], pk["c_nodes"], pk["c_vars"]]
                    if pk["readback"] != want or pk["g_nodes"] > b["B_nodes"] or pk["g_vars"] > b["B_vars"]:
                        fail(f"fabric {name}({N}) {W}x{H}: peak {pk['g_nodes']}/{pk['g_vars']} > {b['B_nodes']}/{b['B_vars']} or {pk['readback']}")
            rows.append(row)
    if use_rtl:
        from omega import rtl
        for name, N in RTL_AT:
            book = progs.book(name, N); want = progs.expected(name, N); b = eal.bound(book)
            row = next(r for r in rows if r["prog"] == name and r["N"] == N) if any(r["prog"] == name and r["N"] == N for r in rows) else None
            if row is None:
                rs = sem_peaks(book)
                row = {"prog": name, "N": N, "B_nodes": b["B_nodes"], "B_vars": b["B_vars"], "lifo": [rs[0]["peak_nodes"], rs[0]["peak_vars"]],
                       "fifo": [rs[1]["peak_nodes"], rs[1]["peak_vars"]], "random": [max(r["peak_nodes"] for r in rs[2:]), max(r["peak_vars"] for r in rs[2:])],
                       "slots_mesh": b["slots_mesh"], "interactions": b["interactions"]}
                rows.append(row)
            n += 1
            r = rtl.run(book, 1, 1, slots=4096 if b["slots_1x1"] > 1000 else 1024, seed=2)
            c = r["cells"][(0, 0)]
            row["rtl_1x1"] = [c["peak_nodes"], c["peak_vars"], r.get("cycles")]
            if r["readback"] != want or c["peak_nodes"] > b["B_nodes"] or c["peak_vars"] > b["B_vars"]:
                fail(f"rtl 1x1 {name}({N}): peak {c['peak_nodes']}/{c['peak_vars']} > {b['B_nodes']}/{b['B_vars']} or {r['readback']}")
            n += 1
            ok, pn, pv, cyc, st = rtl_at_bound(book, b, want)
            row["rtl_at_bound"] = [pn, pv, cyc, st]
            if not ok or pn > b["B_nodes"] or pv > b["B_vars"]:
                fail(f"rtl 1x1 with B slots {name}({N}): status {st}, live peak {pn}/{pv} vs {b['B_nodes']}/{b['B_vars']}")
        for name, N in MESH_AT:
            book = progs.book(name, N); want = progs.expected(name, N); b = eal.bound(book)
            n += 1
            ok, st = rtl_mesh_at_bound(book, b, want)
            rows.append({"prog": name, "N": N, "mesh_2x2_at_slots_mesh": [b["slots_mesh"], st]})
            if not ok: fail(f"rtl 2x2 with slots_mesh per cell {name}({N}): status {st}")
    if fuzz_k:
        log = open(out.replace(".json", "_fuzz.jsonl"), "w") if out else None
        k, f = fuzz(fuzz_k, rtl_fuzz if use_rtl else 0, verbose=verbose, log=log)
        n += k; fails += f
    if out:
        json.dump(rows, open(out, "w"), indent=1)
    if verbose:
        print(f"Ω-L tests: {n - fails}/{n} pass ({time.time() - t0:.0f}s)" + (" [checker + semantic + fabric + RTL]" if use_rtl else " [checker + semantic + fabric]"))
    return n, fails


MUTANTS = {1: "affinity check off (data may be duplicated)", 2: "any closure may be passed to a !-parameter",
           3: "termination (measure) check off", 4: "bound: commutation node deltas not counted",
           5: "constructor fields typed freshly per use (functions can hide in data)", 6: "numeric guards (`if n < c`) ignored",
           7: "bound: commutation var allocations not counted"}


def main():
    if "--mutants" in sys.argv:
        caught = 0
        for m, what in MUTANTS.items():
            eal.MUT = m
            _, f = run(use_rtl=False, fuzz_k=12, verbose=False)
            caught += f > 0
            print(f"eal mutant {m} ({what}): {'caught' if f else 'SURVIVED'} ({f} failures)", flush=True)
        eal.MUT = 0
        print(f"Ω-L mutants: {caught}/{len(MUTANTS)} caught")
        return 0 if caught == len(MUTANTS) else 1
    fz = int(sys.argv[sys.argv.index("--fuzz") + 1]) if "--fuzz" in sys.argv else 0
    rf = int(sys.argv[sys.argv.index("--rtl-fuzz") + 1]) if "--rtl-fuzz" in sys.argv else 0
    out = sys.argv[sys.argv.index("--json") + 1] if "--json" in sys.argv else None
    _, f = run(use_rtl="--no-rtl" not in sys.argv, fuzz_k=fz, rtl_fuzz=rf, out=out)
    return 1 if f else 0


if __name__ == "__main__":
    sys.exit(main())
