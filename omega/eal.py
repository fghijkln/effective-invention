"""Ω-L (step 24): a light-affine, stratified subset of Ω-lang with a compile-time peak-memory bound.

Rules (SPEC §7.2).  A program is in Ω-L when, on top of the ordinary Ω-lang checks:
  T  it is Hindley–Milner typed with *monomorphic, first-order constructor fields*: every field of a
     constructor has one type in the whole program (not a fresh type per use, as `typecheck.py` allows),
     and no field holds a function;
  A  every binder of a non-number type is used at most once in every net template the compiler emits
     (counted exactly as `Compiler.compile_def` counts uses, after arm lifting, so an inline value arm
     shares its binders with its siblings);
  !  a binder of function type may be used several times only if it is a parameter of its definition
     (a "!-parameter"), and every call site passes there an *inert closure*: a λ literal built from its own
     variables, numbers, operators and applications (its free variables numbers or !-parameters of the
     caller), a global definition name, or the caller's own !-parameter.  Box depth is 1: what is
     duplicated never contains a definition reference, so a copy costs at most the literal's node count;
  R  every recursive call (inside a strongly connected component of the call graph) decreases a measure
     parameter of its callee: a structural sub-term of a matched data parameter, or a guarded numeric
     predecessor (`p` of `switch n`, `n - k` / `p - k` where an enclosing guard proves no wrap-around).
     Recursion through a function value is rejected.
Consequences: every reduction of an Ω-L program terminates (well-founded recursion over an SN λ core;
nothing duplicates a data value), so the compiler can afford one *counting run* of the closed program,
and the bound it reads off holds for every schedule:

  B_nodes = n0 + Σ_i max(0, Δnodes_i)      B_vars = v0 + Σ_i vars allocated by interaction i

over the interaction multiset {i}, which strong confluence makes the same for every reduction order
(n0 / v0: the loaded @main template and the root var).  At any moment of any schedule the live node
count is n0 plus the deltas of the interactions done so far, and live vars ≤ vars ever allocated, so
peak ≤ B on the semantic reducer, the fabric model and the RTL alike.

usage:  python3 -m omega.eal FILE.olm [--N n]      python3 -m omega.eal PROGRAM N   (programs/*.olm)
        python3 -m omega.eal --symbolic PROGRAM|FILE.olm [NMAX]   (step 25: B(N) in closed form, omega/symbolic.py)
"""
import os, sys
from . import lang, typecheck as tc, semantic
from .ports import *

MUT = int(os.environ.get("OMEGA_EAL_MUT", "0"))   # checker / bound mutants (tests/test_eal.py); 0 = none


class Reject(Exception):
    pass


# ------------------------------------------------------------------------------------------- T: types
def _infer(comp, e, env, where, rec, ftypes):
    k = e[0]
    if k == "num": return tc.NUM
    if k == "var":
        if e[1] not in env: raise SyntaxError(f"unbound variable {e[1]} in {where}")
        s = env[e[1]]
        return s.inst() if isinstance(s, tc.Scheme) else s
    if k == "lam":
        a = tc.TVar(); rec.setdefault(e[1], []).append(a)
        return tc.fn(a, _infer(comp, e[2], {**env, e[1]: a}, where, rec, ftypes))
    if k == "app":
        f = _infer(comp, e[1], env, where, rec, ftypes); a = _infer(comp, e[2], env, where, rec, ftypes); r = tc.TVar()
        tc.unify(f, tc.fn(a, r), f"{where} (application)")
        return r
    if k == "op":
        for x in (e[2], e[3]):
            tc.unify(_infer(comp, x, env, where, rec, ftypes), tc.NUM, f"{where} (operand of {e[1]})")
        return tc.NUM
    if k == "let":
        t = _infer(comp, e[2], env, where, rec, ftypes); rec.setdefault(e[1], []).append(t)
        return _infer(comp, e[3], {**env, e[1]: tc.generalize(t, env)}, where, rec, ftypes)
    if k == "switch":
        tc.unify(_infer(comp, e[1], env, where, rec, ftypes), tc.NUM, f"{where} (switch / if condition)")
        z = _infer(comp, e[2], env, where, rec, ftypes)
        rec.setdefault(e[3], []).append(tc.NUM)
        s = _infer(comp, e[4], {**env, e[3]: tc.NUM}, where, rec, ftypes)
        tc.unify(z, s, f"{where} (switch / if arms)")
        return z
    if k == "match":
        dt = comp.ctors[e[2][0][0]][0]
        tc.unify(_infer(comp, e[1], env, where, rec, ftypes), ("data", dt), f"{where} (match scrutinee)")
        r = None
        for c, fs, b in e[2]:
            loc = dict(env)
            for f, ft in zip(fs, ftypes[c]):
                v = tc.TVar(); rec.setdefault(f, []).append(v)
                if MUT != 5:          # mutant 5: fields fresh per use (step-6 typing) -> data can smuggle functions
                    tc.unify(v, ft, f"{where} (field of {c}: Ω-L constructor fields have one type)")
                loc[f] = v
            t = _infer(comp, b, loc, where, rec, ftypes)
            if r is None: r = t
            else: tc.unify(r, t, f"{where} (match arms)")
        return r
    raise ValueError(k)


def infer_types(comp, user):
    """HM with monomorphic constructor fields.  Returns ({def: {binder name: [types]}}, {ctor: [field types]})."""
    env, ftypes = {}, {}
    for c, (dt, _, fs) in comp.ctors.items():
        ftypes[c] = [tc.TVar() for _ in fs]
        t = ("data", dt)
        for v in reversed(ftypes[c]): t = tc.fn(v, t)
        env[c] = t if MUT != 5 else tc.Scheme(ftypes[c], t)
    names = set(user)
    edges = {n: sorted(tc.refs(user[n], names, set())) for n in user}
    recs = {n: {} for n in user}
    for group in tc.sccs(list(user), edges):
        mono = {n: tc.TVar() for n in group}
        local = dict(env); local.update(mono)
        for n in group:
            try:
                tc.unify(mono[n], _infer(comp, user[n], local, n, recs[n], ftypes), n)
            except TypeError as ex:
                raise Reject(f"type: {ex}")
        for n in group:
            env[n] = tc.generalize(mono[n], env)
    for c, ts in ftypes.items():
        for i, t in enumerate(ts):
            t = tc.prune(t)
            if isinstance(t, tuple) and t[0] == "->":
                raise Reject(f"type: field {i + 1} of constructor {c} holds a function ({tc.show(t)}); Ω-L data is first order")
    return recs, ftypes, edges


def _is_num(t): t = tc.prune(t); return isinstance(t, tuple) and t[0] == "Num"
def _is_fun(t): t = tc.prune(t); return isinstance(t, tuple) and t[0] == "->"


# ------------------------------------------------------------------------- A, !: template use counts
def resolved_defs(comp):
    """The lifted, resolved ASTs exactly as Compiler.compile builds them (same order)."""
    comp.pending = []
    out = {}
    for n in comp.order:
        out[n] = comp.resolve(comp.defs[n], frozenset(), n)
    while comp.pending:
        n, ast = comp.pending.pop(0)
        comp.globals.add(n)
        out[n] = comp.resolve(ast, frozenset(), n)
    return out


def template_uses(ast):
    """[(binder name, uses)] for one template, counted like Compiler.compile_def (vars + switch fv lists)."""
    uses, names, nb = {}, {}, [0]

    def bind(x):
        nb[0] += 1; names[nb[0]] = x; uses[nb[0]] = 0; return nb[0]

    def go(e, env):
        k = e[0]
        if k == "var": uses[env[e[1]]] += 1
        elif k == "lam": go(e[2], {**env, e[1]: bind(e[1])})
        elif k == "app": go(e[1], env); go(e[2], env)
        elif k == "op": go(e[2], env); go(e[3], env)
        elif k == "let": go(e[2], env); go(e[3], {**env, e[1]: bind(e[1])})
        elif k == "switch":
            go(e[1], env); go(e[2], env); go(e[3], env)
            for x in e[4]: uses[env[x]] += 1
    go(ast, {})
    return [(names[b], uses[b]) for b in uses]


def params(ast):
    ps = []
    while ast[0] == "lam":
        ps.append(ast[1]); ast = ast[2]
    return ps, ast


def spine(e):
    args = []
    while e[0] == "app":
        args.append(e[2]); e = e[1]
    return e, args[::-1]


def binders(e, acc):
    k = e[0]
    if k == "lam": acc.append(e[1]); binders(e[2], acc)
    elif k == "app": binders(e[1], acc); binders(e[2], acc)
    elif k == "op": binders(e[2], acc); binders(e[3], acc)
    elif k == "let": acc.append(e[1]); binders(e[2], acc); binders(e[3], acc)
    elif k == "switch": binders(e[1], acc); binders(e[2], acc); acc.append(e[3]); binders(e[4], acc)
    elif k == "match":
        binders(e[1], acc)
        for _, fs, b in e[2]: acc.extend(fs); binders(b, acc)
    return acc


def inert(e, local, ok_free, globals_):
    """λ literal / value that is safe to duplicate: no definition reference applied inside, no switch / match."""
    k = e[0]
    if k == "num": return True
    if k == "var": return e[1] in local or e[1] in ok_free
    if k == "lam": return inert(e[2], local | {e[1]}, ok_free, globals_)
    if k == "app": return inert(e[1], local, ok_free, globals_) and inert(e[2], local, ok_free, globals_)
    if k == "op": return inert(e[2], local, ok_free, globals_) and inert(e[3], local, ok_free, globals_)
    if k == "let": return inert(e[2], local, ok_free, globals_) and inert(e[3], local | {e[1]}, ok_free, globals_)
    return False


def check_bang(user, recs, res, ctors):
    """A and ! rules.  Returns {def: {param index}} of !-parameters."""
    bang = {}
    for t, ast in res.items():
        if t in ctors: continue
        root = t.split("__")[0]
        if root not in user: continue
        for x, u in template_uses(ast):
            if u <= 1: continue
            ts = recs[root].get(x, [])
            if ts and all(_is_num(s) for s in ts): continue
            if MUT == 1: continue                     # mutant 1: no affinity check
            if not ts or not all(_is_fun(s) for s in ts):
                shown = tc.show(ts[0]) if ts else "?"
                raise Reject(f"affine: {root}: `{x}` ({shown}) is used {u} times in template {t}; Ω-L duplicates only numbers and !-closures")
            ps, _ = params(user[root])
            if x not in ps or binders(user[root], []).count(x) != 1:
                raise Reject(f"bang: {root}: function `{x}` is used {u} times but is not a parameter of {root} (only !-parameters may be duplicated)")
            bang.setdefault(root, set()).add(ps.index(x))
    # every call site of a definition with !-parameters passes inert closures there
    for f, ast in user.items():
        fps, _ = params(ast)
        num_ok = {x for x, ts in recs[f].items() if ts and all(_is_num(s) for s in ts)}
        mine = {fps[i] for i in bang.get(f, ())}

        def walk(e, bound):
            k = e[0]
            if k == "app" or (k == "var" and e[1] in bang and e[1] not in bound):
                h, args = spine(e)
                if h[0] == "var" and h[1] in bang and h[1] not in bound:
                    for i in bang[h[1]]:
                        if i >= len(args):
                            raise Reject(f"bang: {f}: {h[1]} is used without its !-argument {i + 1} (partial application)")
                        a = args[i]
                        good = (a[0] == "var" and (a[1] in mine or (a[1] in user and a[1] not in bound))) or \
                               (a[0] == "lam" and inert(a, set(), num_ok | mine, user))
                        if not good and MUT != 2:          # mutant 2: any closure may be duplicated
                            raise Reject(f"bang: {f}: argument {i + 1} of {h[1]} must be an inert closure (λ literal over its own variables, numbers, operators), a definition name or a !-parameter")
                    for a in args: walk(a, bound)
                    return
                if k == "app":
                    walk(e[1], bound); walk(e[2], bound)
                return
            if k == "lam": walk(e[2], bound | {e[1]})
            elif k == "op": walk(e[2], bound); walk(e[3], bound)
            elif k == "let": walk(e[2], bound); walk(e[3], bound | {e[1]})
            elif k == "switch": walk(e[1], bound); walk(e[2], bound); walk(e[4], bound | {e[3]})
            elif k == "match":
                walk(e[1], bound)
                for _, fs, b in e[2]: walk(b, bound | set(fs))
        walk(ast, set())
    return bang


# ------------------------------------------------------------------------------------ R: recursion
def _calls(f, ast, scc, nparams):
    """Intra-SCC call sites of f: [(callee, args, facts)].  facts: sym {var: (j, d)} (var = param_j - d),
    lb {j: k} (param_j >= k), sub {var: j} (var is a strict sub-term of data param j)."""
    ps, body = params(ast)
    out = []

    def go(e, sym, lb, sub, bound):
        k = e[0]
        if k == "var":
            if e[1] in scc and e[1] not in bound:
                raise Reject(f"recursion: {f}: {e[1]} is used as a function value (recursion through a value is not in Ω-L)")
            return
        if k == "app":
            h, args = spine(e)
            if h[0] == "var" and h[1] in scc and h[1] not in bound:
                if len(args) < nparams[h[1]]:
                    raise Reject(f"recursion: {f}: partial application of recursive {h[1]}")
                out.append((h[1], args, dict(sym), dict(lb), dict(sub)))
            else:
                go(h, sym, lb, sub, bound)
            for a in args: go(a, sym, lb, sub, bound)
            return
        if k == "num": return
        if k == "lam":
            go(e[2], {x: v for x, v in sym.items() if x != e[1]}, lb, {x: v for x, v in sub.items() if x != e[1]}, bound | {e[1]})
        elif k == "op": go(e[2], sym, lb, sub, bound); go(e[3], sym, lb, sub, bound)
        elif k == "let":
            go(e[2], sym, lb, sub, bound)
            s2 = {x: v for x, v in sym.items() if x != e[1]}; u2 = {x: v for x, v in sub.items() if x != e[1]}
            if e[2][0] == "var":
                if e[2][1] in sym: s2[e[1]] = sym[e[2][1]]
                if e[2][1] in sub: u2[e[1]] = sub[e[2][1]]
            go(e[3], s2, lb, u2, bound | {e[1]})
        elif k == "switch":
            c = e[1]
            go(c, sym, lb, sub, bound)
            lz, ls = dict(lb), dict(lb)
            sp = {x: v for x, v in sym.items() if x != e[3]}
            if c[0] == "var" and c[1] in sym:
                j, d = sym[c[1]]
                ls[j] = max(ls.get(j, 0), d + 1)
                sp[e[3]] = (j, d + 1)
            elif c[0] == "op" and c[2][0] == "var" and c[2][1] in sym and c[3][0] == "num" and MUT != 6:
                j, d = sym[c[2][1]]; n = c[3][1]
                if c[1] == "<": lz[j] = max(lz.get(j, 0), d + n)         # zero arm: not (x < n)
                elif c[1] == "<=": lz[j] = max(lz.get(j, 0), d + n + 1)
                elif c[1] == ">=": ls[j] = max(ls.get(j, 0), d + n)
                elif c[1] == ">": ls[j] = max(ls.get(j, 0), d + n + 1)
                elif c[1] == "!=" and n == 0: ls[j] = max(ls.get(j, 0), d + 1)
                elif c[1] == "==" and n == 0: lz[j] = max(lz.get(j, 0), d + 1)
            go(e[2], sym, lz, sub, bound)
            go(e[4], sp, ls, {x: v for x, v in sub.items() if x != e[3]}, bound | {e[3]})
        elif k == "match":
            go(e[1], sym, lb, sub, bound)
            sc = e[1]
            for _, fs, b in e[2]:
                u2 = {x: v for x, v in sub.items() if x not in fs}
                s2 = {x: v for x, v in sym.items() if x not in fs}
                if sc[0] == "var" and (sc[1] in sub or sc[1] in dataparam):
                    for x in fs: u2[x] = sub.get(sc[1], dataparam.get(sc[1]))
                go(b, s2, lb, u2, bound | set(fs))
    dataparam = {x: j for j, x in enumerate(ps)}
    go(body, {x: (j, 0) for j, x in enumerate(ps)}, {}, {}, set())
    return out


def _decreases(a, j, sym, lb, sub):
    if MUT == 3: return True                              # mutant 3: no termination check
    if a[0] == "var":
        if sub.get(a[1]) == j: return True
        if a[1] in sym:
            jj, d = sym[a[1]]
            return jj == j and d >= 1 and lb.get(j, 0) >= d
        return False
    if a[0] == "op" and a[1] == "-" and a[2][0] == "var" and a[2][1] in sym and a[3][0] == "num":
        jj, d = sym[a[2][1]]; c = a[3][1]
        return jj == j and d + c >= 1 and lb.get(j, 0) >= d + c
    return False


def check_recursion(user, edges):
    """R rule.  Returns {def: (measure param index, kind, fan-out)} for recursive definitions."""
    out = {}
    nparams = {f: len(params(user[f])[0]) for f in user}
    for group in tc.sccs(list(user), edges):
        scc = set(group)
        if len(group) == 1 and group[0] not in edges[group[0]]: continue
        calls = {f: _calls(f, user[f], scc, nparams) for f in group}
        choice = None

        def search(i, m):
            nonlocal choice
            if choice is not None: return
            if i == len(group):
                if all(m[g] < len(args) and _decreases(args[m[g]], m[f], sym, lb, sub) for f in group for g, args, sym, lb, sub in calls[f]):
                    choice = dict(m)
                return
            for j in range(max(1, nparams[group[i]])):
                m[group[i]] = j; search(i + 1, m)
        search(0, {})
        if choice is None:
            bad = [(f, c[0]) for f in group for c in calls[f]
                   if not any(_decreases(c[1][j], jf, *c[2:]) for j in range(len(c[1])) for jf in range(nparams[f]))]
            f, g = bad[0] if bad else (group[0], group[0])
            raise Reject(f"recursion: {f}: call {g}(…) does not decrease a measure parameter (Ω-L recursion is structural or on a guarded numeric predecessor)")
        for f in group:
            kind = "structural" if any(sub.get(args[choice[g]][1]) == choice[f] for g, args, _, _, sub in calls[f]
                                       if args[choice[g]][0] == "var") else "numeric"
            out[f] = (choice[f], kind, _fanout(user[f], scc))
    return out


def _fanout(e, scc):
    """Largest number of intra-SCC calls on one path (switch / match arms are alternatives)."""
    k = e[0]
    if k == "app":
        h, args = spine(e)
        return (1 if h[0] == "var" and h[1] in scc else _fanout(h, scc)) + sum(_fanout(a, scc) for a in args)
    if k == "lam": return _fanout(e[2], scc)
    if k == "op": return _fanout(e[2], scc) + _fanout(e[3], scc)
    if k == "let": return _fanout(e[2], scc) + _fanout(e[3], scc)
    if k == "switch": return _fanout(e[1], scc) + max(_fanout(e[2], scc), _fanout(e[4], scc))
    if k == "match": return _fanout(e[1], scc) + max(_fanout(b, scc) for _, _, b in e[2])
    return 0


# ---------------------------------------------------------------------------------------- checker
def check(src):
    """Ω-L check of an Ω-lang source.  Returns a report dict; report["ok"] False with report["reason"]."""
    try:
        comp = lang.Compiler(src)                    # parse, patterns, step-6 HM types
    except (SyntaxError, TypeError) as ex:
        return {"ok": False, "reason": f"Ω-lang: {ex}"}
    user = {n: comp.defs[n] for n in comp.order if n not in comp.ctors}
    try:
        recs, ftypes, edges = infer_types(comp, user)
        res = resolved_defs(comp)
        bang = check_bang(user, recs, res, comp.ctors)
        rec = check_recursion(user, edges)
    except Reject as ex:
        return {"ok": False, "reason": str(ex)}
    return {"ok": True, "bang": {f: sorted(s) for f, s in bang.items()}, "recursion": rec, "types": comp.types}


# ------------------------------------------------------------------------------------------ bound
class CountNet(semantic.Net):
    """Semantic reducer that also records positive node deltas, var allocations and peaks."""
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.var_alloc = self.dnodes = self.peak_nodes = self.peak_vars = 0

    def alloc_var(self, o=0):
        self.var_alloc += 1
        v = super().alloc_var(o)
        if len(self.vars) > self.peak_vars: self.peak_vars = len(self.vars)
        return v

    def interact(self, a, b):
        n0, c0 = len(self.nodes), self.stats["comm"]
        super().interact(a, b)
        d = len(self.nodes) - n0
        if d > 0 and not (MUT == 4 and self.stats["comm"] > c0): self.dnodes += d    # mutant 4: commutations not counted
        if len(self.nodes) > self.peak_nodes: self.peak_nodes = len(self.nodes)


def count_run(book, order="lifo", seed=None, fuel=10**8):
    net = CountNet(book)
    root = net.alloc_var()
    net.instantiate(book.id("main"), mk(VAR, 0, root))
    n0, v0 = net.next_node - 1, net.var_alloc
    net.peak_nodes = max(net.peak_nodes, len(net.nodes))
    net.normalize(seed, fuel, order)
    bv = net.var_alloc if MUT != 7 else net.var_alloc - 4 * net.stats["comm"]   # mutant 7: commutation vars not counted
    return {"B_nodes": n0 + net.dnodes, "B_vars": bv, "n0": n0, "v0": v0,
            "peak_nodes": net.peak_nodes, "peak_vars": net.peak_vars, "interactions": net.stats["interactions"],
            "readback": semantic.readback_net(net, root), "stats": dict(net.stats)}


def bound(book, fuel=10**8):
    """Compile-time bound of an Ω-L program (counting run, depth first).  slots_1x1: node = var slots one cell
    needs; slots_mesh: what every cell of a mesh needs so that no cell ever lacks room for an expansion
    (+ the largest template and the low-memory reserve, SPEC §7.2)."""
    from . import fabric
    r = count_run(book, "lifo", fuel=fuel)
    dmax = max(max(len(d.nodes), d.nvars) for d in book.defs)
    s1 = max(r["B_nodes"], r["B_vars"])
    r.update({"dmax": dmax, "slots_1x1": s1, "slots_mesh": s1 + dmax + max(fabric.LM_RSV, fabric.RSV)})
    return r


def growth(rec):
    out = {}
    for f, (j, kind, c) in rec.items():
        out[f] = f"{kind} on parameter {j + 1}, " + ("linear in its size" if kind == "structural" else
                                                       "linear in its value" if c <= 1 else f"≤ {c}^value unfolds")
    return out


def analyse(src, with_bound=True):
    rep = check(src)
    if rep["ok"] and with_bound:
        rep["bound"] = bound(lang.compile_book(src))
        rep["growth"] = growth(rep["recursion"])
    return rep


def main(argv):
    if not argv:
        print(__doc__); return 2
    if argv[0] == "--symbolic":                     # step 25: B as a closed form in N (omega/symbolic.py)
        from . import symbolic
        return symbolic.main(argv[1:])
    if os.path.exists(argv[0]):
        src = open(argv[0]).read()
        if "--N" in argv:
            import re
            src = re.sub(r"\bN\b", argv[argv.index("--N") + 1], src)
        label = argv[0]
    else:
        from . import progs
        src = progs.source(argv[0], int(argv[1])); label = f"{argv[0]}({argv[1]})"
    rep = analyse(src)
    if not rep["ok"]:
        print(f"{label}: not in Ω-L: {rep['reason']}"); return 1
    b = rep["bound"]
    print(f"{label}: in Ω-L")
    for f, g in rep["growth"].items(): print(f"  recursion {f}: {g}")
    for f, ps in rep["bang"].items(): print(f"  !-parameters of {f}: {', '.join(str(i + 1) for i in ps)}")
    print(f"  bound: nodes {b['B_nodes']}, vars {b['B_vars']} (n0 {b['n0']}, v0 {b['v0']}, {b['interactions']} interactions)")
    print(f"  slots: one cell {b['slots_1x1']}, every mesh cell {b['slots_mesh']} (largest template {b['dmax']})")
    print(f"  depth-first peak (semantic): nodes {b['peak_nodes']}, vars {b['peak_vars']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
