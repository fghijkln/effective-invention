"""Basic type checking for Ω-lang (Hindley-Milner with let-polymorphism, no annotations).

Types: Num (u32), the user's data types (one name each, not parameterised), functions, and type
variables.  Constructor fields are untyped in the source, so every use of a constructor gets fresh
field types (lenient: a list may hold numbers in one place and functions in another).  What is
checked is the *shape* of every expression:
* arithmetic, comparison and `switch` / `if` conditions need numbers;
* `match` needs a value of the matched data type;
* only functions can be applied, and with arguments consistent with their definition;
* the arms of a `switch` / `match` have one type;
* `main` is a value, not a function.
Top-level definitions are generalised per strongly connected component of the call graph (a
polymorphic helper can be used at several types; mutual recursion is monomorphic, as in ML).
Raises `TypeError` naming the definition.
"""
import sys


class TVar:
    __slots__ = ("ref", "id")
    n = 0

    def __init__(self):
        TVar.n += 1
        self.id = TVar.n
        self.ref = None


NUM = ("Num",)


def fn(a, b): return ("->", a, b)


def prune(t):
    while isinstance(t, TVar) and t.ref is not None:
        t = t.ref
    return t


def show(t, names=None):
    names = {} if names is None else names
    t = prune(t)
    if isinstance(t, TVar):
        if t.id not in names: names[t.id] = "abcdefghijklmnopqrstuvwxyz"[len(names) % 26] + "'" * (len(names) // 26)
        return names[t.id]
    if t[0] == "->":
        a = show(t[1], names)
        if isinstance(prune(t[1]), tuple) and prune(t[1])[0] == "->": a = f"({a})"
        return f"{a} -> {show(t[2], names)}"
    return "Num" if t[0] == "Num" else t[1]


def occurs(v, t):
    t = prune(t)
    if t is v: return True
    return isinstance(t, tuple) and t[0] == "->" and (occurs(v, t[1]) or occurs(v, t[2]))


def unify(a, b, where):
    a, b = prune(a), prune(b)
    if a is b: return
    if isinstance(a, TVar):
        if occurs(a, b): raise TypeError(f"{where}: infinite type {show(a)} = {show(b)}")
        a.ref = b; return
    if isinstance(b, TVar):
        unify(b, a, where); return
    if a[0] != b[0] or (a[0] == "data" and a[1] != b[1]):
        raise TypeError(f"{where}: type mismatch, {show(a)} vs {show(b)}")
    if a[0] == "->":
        unify(a[1], b[1], where); unify(a[2], b[2], where)


def ftv(t, acc):
    t = prune(t)
    if isinstance(t, TVar): acc.add(t)
    elif t[0] == "->": ftv(t[1], acc); ftv(t[2], acc)
    return acc


class Scheme:
    def __init__(self, vs, t): self.vs, self.t = vs, t

    def inst(self):
        m = {v: TVar() for v in self.vs}

        def go(t):
            t = prune(t)
            if isinstance(t, TVar): return m.get(t, t)
            if t[0] == "->": return fn(go(t[1]), go(t[2]))
            return t
        return go(self.t)


def env_ftv(env):
    acc = set()
    for s in env.values():
        if isinstance(s, Scheme): acc |= ftv(s.t, set()) - set(s.vs)
        else: ftv(s, acc)
    return acc


def generalize(t, env):
    return Scheme(list(ftv(t, set()) - env_ftv(env)), t)


def refs(e, names, acc):
    k = e[0]
    if k == "var":
        if e[1] in names: acc.add(e[1])
    elif k == "lam": refs(e[2], names - {e[1]}, acc)
    elif k == "app": refs(e[1], names, acc); refs(e[2], names, acc)
    elif k == "op": refs(e[2], names, acc); refs(e[3], names, acc)
    elif k == "let": refs(e[2], names, acc); refs(e[3], names - {e[1]}, acc)
    elif k == "switch": refs(e[1], names, acc); refs(e[2], names, acc); refs(e[4], names - {e[3]}, acc)
    elif k == "match":
        refs(e[1], names, acc)
        for _, fs, b in e[2]: refs(b, names - set(fs), acc)
    return acc


def sccs(nodes, edges):
    idx, low, st, on, out, n = {}, {}, [], set(), [], [0]

    def visit(v):
        idx[v] = low[v] = n[0]; n[0] += 1; st.append(v); on.add(v)
        for w in edges[v]:
            if w not in idx: visit(w); low[v] = min(low[v], low[w])
            elif w in on: low[v] = min(low[v], idx[w])
        if low[v] == idx[v]:
            comp = []
            while True:
                w = st.pop(); on.discard(w); comp.append(w)
                if w == v: break
            out.append(comp)
    for v in nodes:
        if v not in idx: visit(v)
    return out          # callees first


def check_program(comp, defs):
    """comp: the Compiler (constructors, data types); defs: [(name, params, desugared body)].
    Returns {definition: type string}."""
    sys.setrecursionlimit(max(10000, sys.getrecursionlimit()))
    env = {}
    for c, (dt, _, fs) in comp.ctors.items():
        vs = [TVar() for _ in fs]          # constructor: f1 -> .. -> fk -> Data, fresh fields per use
        t = ("data", dt)
        for v in reversed(vs): t = fn(v, t)
        env[c] = Scheme(vs, t)
    names = {n for n, _, _ in defs}
    clash = names & set(comp.ctors)
    if clash: raise SyntaxError(f"definition named like a constructor: {sorted(clash)[0]}")
    bodies = {}
    for n, ps, b in defs:
        for x in reversed(ps): b = ("lam", x, b)
        bodies[n] = b
    edges = {n: sorted(refs(bodies[n], names, set())) for n in bodies}
    for group in sccs(list(bodies), edges):
        mono = {n: TVar() for n in group}
        local = dict(env); local.update(mono)
        for n in group:
            unify(mono[n], infer(comp, bodies[n], local, n), n)
        for n in group:
            env[n] = generalize(mono[n], env)
    if "main" in names:
        t = prune(env["main"].t)
        if isinstance(t, tuple) and t[0] == "->":
            raise TypeError(f"main: is a function ({show(t)}); main must be a value")
    return {n: show(env[n].t) for n in sorted(names)}


def infer(comp, e, env, where):
    k = e[0]
    if k == "num": return NUM
    if k == "var":
        if e[1] not in env: raise SyntaxError(f"unbound variable {e[1]} in {where}")
        s = env[e[1]]
        return s.inst() if isinstance(s, Scheme) else s
    if k == "lam":
        a = TVar()
        return fn(a, infer(comp, e[2], {**env, e[1]: a}, where))
    if k == "app":
        f = infer(comp, e[1], env, where); a = infer(comp, e[2], env, where); r = TVar()
        unify(f, fn(a, r), f"{where} (application)")
        return r
    if k == "op":
        unify(infer(comp, e[2], env, where), NUM, f"{where} (operand of {e[1]})")
        unify(infer(comp, e[3], env, where), NUM, f"{where} (operand of {e[1]})")
        return NUM
    if k == "let":
        t = infer(comp, e[2], env, where)
        return infer(comp, e[3], {**env, e[1]: generalize(t, env)}, where)
    if k == "switch":
        unify(infer(comp, e[1], env, where), NUM, f"{where} (switch / if condition)")
        z = infer(comp, e[2], env, where)
        s = infer(comp, e[4], {**env, e[3]: NUM}, where)
        unify(z, s, f"{where} (switch / if arms)")
        return z
    if k == "match":
        dt = comp.ctors[e[2][0][0]][0]
        unify(infer(comp, e[1], env, where), ("data", dt), f"{where} (match scrutinee)")
        r = None
        for c, fs, b in e[2]:
            t = infer(comp, b, {**env, **{f: TVar() for f in fs}}, where)
            if r is None: r = t
            else: unify(r, t, f"{where} (match arms)")
        return r
    raise ValueError(k)
