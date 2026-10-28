"""Ω-lang: a tiny Bend/Latent-style functional language compiled to the TACHYON-Ω text IR.

    data List = Nil | Cons(h, t)
    def map(f, xs) = match xs { Nil => Nil; Cons(h, t) => Cons(f(h), map(f, t)) }
    def fib(n) = if n < 2 then n else fib(n - 1) + fib(n - 2)
    def sum(n) = switch n { 0 => 0; p => n + sum(p) }      // p = n - 1
    def main = fib(20)

Expressions: numbers (u32), variables, \\x y -> e, f(a, b) (curried), let x = e in b,
if c then a else b, switch e { 0 => a; p => b }, match e { C(x..) => a; ... }, binary operators
+ - * / % == != < > <= >= & | ^ << >>.  Data types are Scott-encoded.  Every switch/match arm that
could do work when it is *not* taken (it contains an application or a nested switch/match) is
lifted into its own closed definition so that it stays a lazy REF until selected (as Bend does).
"""
import re
from . import ir

KW = {"def", "data", "let", "in", "if", "then", "else", "switch", "match"}
TOKRE = re.compile(r"\s*(?:(//[^\n]*)|(\d+)|([A-Za-z_][\w']*)|(=>|->|==|!=|<=|>=|<<|>>|[-+*/%<>&|^(){};,=\\]))")


def tokenize(src):
    toks, pos = [], 0
    src = src.rstrip()
    while pos < len(src):
        m = TOKRE.match(src, pos)
        if not m:
            raise SyntaxError(f"bad character at {src[pos:pos+20]!r}")
        pos = m.end()
        if m.group(1): continue
        if m.group(2): toks.append(("num", int(m.group(2))))
        elif m.group(3): toks.append(("kw" if m.group(3) in KW else "id", m.group(3)))
        else: toks.append(("op", m.group(4)))
    toks.append(("eof", None))
    return toks


# AST: tuples
#   ("num", n) ("var", x) ("ref", name) ("lam", x, body) ("app", f, a) ("op", o, a, b)
#   ("let", x, e, b) ("switch", e, z, p, s) ("match", e, [(ctor, [fields], body)])
BINOPS = [["|"], ["^"], ["&"], ["==", "!="], ["<", ">", "<=", ">="], ["<<", ">>"], ["+", "-"], ["*", "/", "%"]]


class P:
    def __init__(self, src):
        self.t = tokenize(src); self.i = 0

    def peek(self, k=0): return self.t[self.i + k]

    def next(self):
        t = self.t[self.i]; self.i += 1; return t

    def accept(self, v):
        if self.peek()[1] == v and self.peek()[0] in ("op", "kw"):
            self.i += 1; return True
        return False

    def expect(self, v):
        if not self.accept(v):
            raise SyntaxError(f"expected {v!r}, got {self.peek()[1]!r}")

    def ident(self):
        k, v = self.next()
        if k != "id": raise SyntaxError(f"expected identifier, got {v!r}")
        return v

    def program(self):
        datas, defs = [], []
        while self.peek()[0] != "eof":
            if self.accept("data"):
                name = self.ident(); self.expect("=")
                ctors = []
                while True:
                    c = self.ident(); fs = []
                    if self.accept("("):
                        fs = self.idlist(")")
                    ctors.append((c, fs))
                    if not self.accept("|"): break
                datas.append((name, ctors))
            elif self.accept("def"):
                name = self.ident(); ps = []
                if self.accept("("):
                    ps = self.idlist(")")
                self.expect("=")
                defs.append((name, ps, self.expr()))
            else:
                raise SyntaxError(f"expected def/data, got {self.peek()[1]!r}")
        return datas, defs

    def idlist(self, close):
        xs = []
        if self.accept(close): return xs
        while True:
            xs.append(self.ident())
            if self.accept(close): return xs
            self.expect(",")

    def expr(self):
        if self.accept("let"):
            x = self.ident(); self.expect("="); e = self.expr(); self.expect("in")
            return ("let", x, e, self.expr())
        if self.accept("if"):
            c = self.expr(); self.expect("then"); a = self.expr(); self.expect("else"); b = self.expr()
            return ("switch", c, b, "_", a)
        if self.accept("\\"):
            xs = []
            while not self.accept("->"):
                xs.append(self.ident())
            body = self.expr()
            for x in reversed(xs): body = ("lam", x, body)
            return body
        if self.accept("switch"):
            e = self.expr(); self.expect("{")
            k, v = self.next()
            if (k, v) != ("num", 0): raise SyntaxError("switch: first case must be 0")
            self.expect("=>"); z = self.expr(); self.expect(";")
            p = self.ident(); self.expect("=>"); s = self.expr(); self.accept(";"); self.expect("}")
            return ("switch", e, z, p, s)
        if self.accept("match"):
            e = self.expr(); self.expect("{"); arms = []
            while not self.accept("}"):
                pat = self.pattern()
                self.expect("=>"); arms.append((pat, self.expr())); self.accept(";")
            return ("pmatch", e, arms)
        return self.binop(0)

    def pattern(self):
        """pattern := ident | ident '(' pattern, ... ')' | number.  Whether an identifier is a
        constructor or a binder ('_' = wildcard) is decided after parsing (constructors may be declared later)."""
        k, v = self.next()
        if k == "num": return ("pnum", v)
        if k != "id": raise SyntaxError(f"expected a pattern, got {v!r}")
        if self.accept("("):
            subs = []
            if not self.accept(")"):
                while True:
                    subs.append(self.pattern())
                    if self.accept(")"): break
                    self.expect(",")
            return ("pcon", v, subs)
        return ("pid", v)

    def binop(self, lvl):
        if lvl == len(BINOPS): return self.app()
        a = self.binop(lvl + 1)
        while self.peek()[0] == "op" and self.peek()[1] in BINOPS[lvl]:
            o = self.next()[1]
            a = ("op", o, a, self.binop(lvl + 1))
        return a

    def app(self):
        f = self.atom()
        while self.peek() == ("op", "("):
            self.next()
            args = []
            if not self.accept(")"):
                while True:
                    args.append(self.expr())
                    if self.accept(")"): break
                    self.expect(",")
            for a in args: f = ("app", f, a)
        return f

    def atom(self):
        k, v = self.next()
        if k == "num": return ("num", v)
        if k == "id": return ("var", v)
        if (k, v) == ("op", "("):
            e = self.expr(); self.expect(")"); return e
        raise SyntaxError(f"unexpected {v!r}")


# ---------------------------------------------------------------------------------------------
def free_vars(e, bound=frozenset()):
    k = e[0]
    if k == "var": return set() if e[1] in bound else {e[1]}
    if k in ("num", "ref"): return set()
    if k == "lam": return free_vars(e[2], bound | {e[1]})
    if k == "app": return free_vars(e[1], bound) | free_vars(e[2], bound)
    if k == "op": return free_vars(e[2], bound) | free_vars(e[3], bound)
    if k == "let": return free_vars(e[2], bound) | free_vars(e[3], bound | {e[1]})
    if k == "switch": return free_vars(e[1], bound) | free_vars(e[2], bound) | free_vars(e[4], bound | {e[3]})
    if k == "match":
        s = free_vars(e[1], bound)
        for _, fs, b in e[2]: s |= free_vars(b, bound | set(fs))
        return s
    raise ValueError(k)


def needs_lift(e):
    """True if the term contains something that can reduce while the arm is not selected."""
    k = e[0]
    if k in ("app", "switch", "match", "ref"): return True
    if k in ("num", "var"): return False
    if k == "lam": return needs_lift(e[2])
    if k == "op": return needs_lift(e[2]) or needs_lift(e[3])
    if k == "let": return needs_lift(e[2]) or needs_lift(e[3])
    raise ValueError(k)


class Desugar:
    """Nested pattern matching -> flat Scott matches (one level, every constructor, variable fields),
    numeric literal patterns -> `==` tests, `_` / variable patterns -> defaults (column-wise match
    compilation).  Also checks patterns: constructor arity, duplicate binders, exhaustiveness and
    redundant arms."""

    def __init__(self, comp):
        self.c = comp

    def fresh(self):
        self.c.gensym += 1
        return f"%m{self.c.gensym}"

    def expr(self, e, owner):
        k = e[0]
        if k in ("num", "var"): return e
        if k == "lam": return ("lam", e[1], self.expr(e[2], owner))
        if k == "app": return ("app", self.expr(e[1], owner), self.expr(e[2], owner))
        if k == "op": return ("op", e[1], self.expr(e[2], owner), self.expr(e[3], owner))
        if k == "let": return ("let", e[1], self.expr(e[2], owner), self.expr(e[3], owner))
        if k == "switch": return ("switch", self.expr(e[1], owner), self.expr(e[2], owner), e[3], self.expr(e[4], owner))
        if k == "pmatch": return self.match(self.expr(e[1], owner), [(self.pat(p, owner), self.expr(b, owner)) for p, b in e[2]], owner)
        raise ValueError(k)

    def pat(self, p, owner, seen=None):
        """Normalise a parsed pattern: ('con', C, [subs]) | ('num', n) | ('bind', x) | ('wild',)."""
        seen = set() if seen is None else seen
        if p[0] == "pnum": return ("num", p[1] & 0xFFFFFFFF)
        if p[0] == "pcon" or p[1] in self.c.ctors:
            c = p[1]; subs = p[2] if p[0] == "pcon" else []
            if c not in self.c.ctors: raise SyntaxError(f"unknown constructor {c} in a pattern of {owner}")
            ar = len(self.c.ctors[c][2])
            if len(subs) != ar: raise SyntaxError(f"constructor {c} has {ar} field(s), a pattern in {owner} gives {len(subs)}")
            return ("con", c, [self.pat(q, owner, seen) for q in subs])
        if p[1] == "_": return ("wild",)
        if p[1] in seen: raise SyntaxError(f"variable {p[1]} bound twice in one pattern of {owner}")
        seen.add(p[1])
        return ("bind", p[1])

    def match(self, scr, arms, owner):
        # one level, every constructor of one type exactly once, variable / wildcard fields: unchanged
        if arms and all(p[0] == "con" and all(q[0] in ("bind", "wild") for q in p[2]) for p, _ in arms):
            cs = [p[1] for p, _ in arms]
            dt = self.c.ctors[cs[0]][0]
            if len(set(cs)) == len(cs) and set(cs) == set(self.c.datas[dt]):
                return ("match", scr, [(p[1], [q[1] if q[0] == "bind" else self.fresh() for q in p[2]], b) for p, b in arms])
        used = [False] * len(arms)
        rows = [([p], [], b, i) for i, (p, b) in enumerate(arms)]
        if scr[0] == "var":
            out = self.compile([scr[1]], rows, used, owner)
        else:
            s = self.fresh()
            out = ("let", s, scr, self.compile([s], rows, used, owner))
        for i, u in enumerate(used):
            if not u: raise SyntaxError(f"redundant match arm {i + 1} in {owner}")
        return out

    def compile(self, xs, rows, used, owner):
        """xs: scrutinee variable names; rows: (patterns, bindings [(x, var)], body, arm index)."""
        if not rows: raise SyntaxError(f"non-exhaustive match in {owner}")
        pats, binds, body, idx = rows[0]
        if all(p[0] in ("bind", "wild") for p in pats):
            used[idx] = True
            binds = binds + [(p[1], x) for p, x in zip(pats, xs) if p[0] == "bind"]
            for x, v in reversed(binds): body = ("let", x, ("var", v), body)
            return body
        col = next(i for i, p in enumerate(pats) if p[0] not in ("bind", "wild"))
        x = xs[col]
        kinds = {r[0][col][0] for r in rows} - {"bind", "wild"}
        if len(kinds) > 1: raise SyntaxError(f"constructor and number patterns in one position in {owner}")
        if pats[col][0] == "num":
            n = pats[col][1]
            yes, no = [], []
            for ps, bs, b, i in rows:
                p = ps[col]
                if p[0] == "num":
                    if p[1] == n: yes.append((ps[:col] + [("wild",)] + ps[col + 1:], bs, b, i))
                    else: no.append((ps, bs, b, i))
                else:
                    nb = bs + ([(p[1], x)] if p[0] == "bind" else [])
                    yes.append((ps[:col] + [("wild",)] + ps[col + 1:], nb, b, i)); no.append((ps, bs, b, i))
            return ("switch", ("op", "==", ("var", x), ("num", n)), self.compile(xs, no, used, owner), "_",
                    self.compile(xs, yes, used, owner))
        dt = self.c.ctors[pats[col][1]][0]
        out = []
        for c in self.c.datas[dt]:
            ar = len(self.c.ctors[c][2])
            fs = [self.fresh() for _ in range(ar)]
            sub = []
            for ps, bs, b, i in rows:
                p = ps[col]
                if p[0] == "con":
                    if self.c.ctors[p[1]][0] != dt: raise SyntaxError(f"constructors of different types in one position in {owner}")
                    if p[1] == c: sub.append((ps[:col] + p[2] + ps[col + 1:], bs, b, i))
                else:
                    nb = bs + ([(p[1], x)] if p[0] == "bind" else [])
                    sub.append((ps[:col] + [("wild",)] * ar + ps[col + 1:], nb, b, i))
            out.append((c, fs, self.compile(xs[:col] + fs + xs[col + 1:], sub, used, owner)))
        return ("match", ("var", x), out)


class Compiler:
    def __init__(self, src, typecheck=True):
        datas, defs = P(src).program()
        self.ctors = {}      # ctor -> (data, index, fields)
        self.datas = {}
        self.defs = {}       # name -> AST (closed, params as lambdas)
        self.order = []
        for dname, cs in datas:
            if dname in self.datas: raise SyntaxError(f"duplicate data type {dname}")
            self.datas[dname] = [c for c, _ in cs]
            for c, fs in cs:
                if c in self.ctors: raise SyntaxError(f"duplicate constructor {c}")
                if len(set(fs)) != len(fs): raise SyntaxError(f"duplicate field name in constructor {c}")
                self.ctors[c] = (dname, None, fs)
        user = []
        for name, ps, body in defs:
            if len(set(ps)) != len(ps): raise SyntaxError(f"duplicate parameter in {name}")
            self.gensym = 0
            user.append((name, ps, Desugar(self).expr(body, name)))
        self.types = None
        if typecheck:
            from .typecheck import check_program
            self.types = check_program(self, user)
        defs = user
        for dname, cs in datas:
            for i, (c, fs) in enumerate(cs):
                self.ctors[c] = (dname, i, fs)
                cases = [f"c{j}" for j in range(len(cs))]
                body = ("var", cases[i])
                for f in fs: body = ("app", body, ("var", f))
                for x in reversed(fs + cases): body = ("lam", x, body)
                self.add(c, body)
        for name, ps, body in defs:
            for x in reversed(ps): body = ("lam", x, body)
            self.add(name, body)
        self.globals = set(self.defs)
        self.label = 0
        self.lift_n = 0

    def add(self, name, ast):
        if name in self.defs: raise SyntaxError(f"duplicate definition {name}")
        self.defs[name] = ast; self.order.append(name)

    # ---- resolve globals, lift arms ----
    def resolve(self, e, bound, owner):
        k = e[0]
        if k == "var":
            if e[1] in bound: return e
            if e[1] in self.globals: return ("ref", e[1])
            raise SyntaxError(f"unbound variable {e[1]} in {owner}")
        if k in ("num", "ref"): return e
        if k == "lam": return ("lam", e[1], self.resolve(e[2], bound | {e[1]}, owner))
        if k == "app": return ("app", self.resolve(e[1], bound, owner), self.resolve(e[2], bound, owner))
        if k == "op": return ("op", e[1], self.resolve(e[2], bound, owner), self.resolve(e[3], bound, owner))
        if k == "let": return ("let", e[1], self.resolve(e[2], bound, owner), self.resolve(e[3], bound | {e[1]}, owner))
        if k == "switch":
            _, scr, z, p, s = e
            scr = self.resolve(scr, bound, owner)
            if not (needs_lift(z) or needs_lift(s)):
                return ("switch", scr, self.resolve(z, bound, owner),
                        ("lam", p, self.resolve(s, bound | {p}, owner)), [])
            fv = sorted((free_vars(z) | free_vars(s, frozenset({p}))) & bound)
            # only arms that can reduce on their own are lifted; value arms stay inline (\fv.. body)
            zw = self.wrap(z, fv)
            sw = ("lam", p, self.wrap(s, fv))
            zr = self.lift(owner, zw) if needs_lift(z) else self.resolve(zw, bound - set(fv), owner)
            sr = self.lift(owner, sw) if needs_lift(s) else self.resolve(sw, bound - set(fv) - {p}, owner)
            return ("switch", scr, zr, sr, fv)
        if k == "match":
            scr = self.resolve(e[1], bound, owner)
            arms = {c: (fs, b) for c, fs, b in e[2]}
            first = e[2][0][0]
            if first not in self.ctors: raise SyntaxError(f"unknown constructor {first}")
            names = self.datas[self.ctors[first][0]]
            if set(arms) != set(names) or len(arms) != len(e[2]):
                raise SyntaxError(f"match must cover exactly {names}")
            lifted = any(needs_lift(arms[c][1]) for c in names)
            fv = sorted(set().union(*[free_vars(arms[c][1], frozenset(arms[c][0])) for c in names]) & bound)
            out = scr
            for c in names:
                fs, b = arms[c]
                if lifted:
                    arm = self.wrap(b, fv)
                    for f in reversed(fs): arm = ("lam", f, arm)
                    if needs_lift(b):
                        out = ("app", out, self.lift(owner, arm))
                    else:
                        out = ("app", out, self.resolve(arm, bound - set(fv) - set(fs), owner))
                else:
                    arm = self.resolve(b, bound | set(fs), owner)
                    for f in reversed(fs): arm = ("lam", f, arm)
                    out = ("app", out, arm)
            if lifted:
                for x in fv: out = ("app", out, ("var", x))
            return out
        raise ValueError(k)

    def wrap(self, body, fv):
        for x in reversed(fv): body = ("lam", x, body)
        return body

    def lift(self, owner, body):
        self.lift_n += 1
        name = f"{owner}__a{self.lift_n}"
        self.globals.add(name)
        self.pending.append((name, body))
        return ("ref", name)

    # ---- compile to IR text ----
    def compile_def(self, name, ast):
        self.vn = 0
        rdx = []
        uses = {}

        def count(e, env):
            k = e[0]
            if k == "var": uses[env[e[1]]] = uses.get(env[e[1]], 0) + 1
            elif k == "lam":
                b = self.fresh_binder(e[1]); count(e[2], {**env, e[1]: b})
            elif k == "app": count(e[1], env); count(e[2], env)
            elif k == "op": count(e[2], env); count(e[3], env)
            elif k == "let":
                count(e[2], env); b = self.fresh_binder(e[1]); count(e[3], {**env, e[1]: b})
            elif k == "switch":
                count(e[1], env); count(e[2], env); count(e[3], env)
                for x in e[4]: uses[env[x]] = uses.get(env[x], 0) + 1
        # binder ids are allocated in the same order by count() and go()
        self.bid = 0
        count(ast, {})
        self.bid = 0
        occ = {}

        def fresh():
            self.vn += 1; return f"v{self.vn}"

        def bind(b):
            n = uses.get(b, 0)
            if n == 0: return "*"
            names = [fresh() for _ in range(n)]
            occ[b] = names
            if n == 1: return names[0]
            self.label += 1
            lab = self.label
            t = names[-1]
            for x in reversed(names[:-1]): t = f"{{{lab} {x} {t}}}"
            return t

        def use(b):
            return occ[b].pop()

        def go(e, env):
            k = e[0]
            if k == "num": return f"#{e[1] & 0xFFFFFFFF}"
            if k == "ref": return f"@{e[1]}"
            if k == "var": return use(env[e[1]])
            if k == "lam":
                b = self.fresh_binder(e[1]); pat = bind(b)
                return f"({pat} {go(e[2], {**env, e[1]: b})})"
            if k == "app":
                f = go(e[1], env); a = go(e[2], env); r = fresh()
                rdx.append(f"{f} ~ ({a} {r})"); return r
            if k == "op":
                a = go(e[2], env); bb = go(e[3], env); r = fresh()
                rdx.append(f"{a} ~ $({e[1]} {bb} {r})"); return r
            if k == "let":
                v = go(e[2], env)
                b = self.fresh_binder(e[1]); pat = bind(b)
                rdx.append(f"{pat} ~ {v}") if pat != "*" else rdx.append(f"* ~ {v}")
                return go(e[3], {**env, e[1]: b})
            if k == "switch":
                scr = go(e[1], env); z = go(e[2], env); s = go(e[3], env); r = fresh()
                rdx.append(f"{scr} ~ ?(({z} {s}) {r})")
                for x in e[4]:
                    a = use(env[x]); r2 = fresh()
                    rdx.append(f"{r} ~ ({a} {r2})"); r = r2
                return r
            raise ValueError(k)
        root = go(ast, {})
        return f"@{name} = {root}" + "".join(f"\n  & {x}" for x in rdx)

    def fresh_binder(self, x):
        self.bid += 1
        return self.bid

    def compile(self):
        out = []
        self.pending = []
        work = list(self.order)
        resolved = {}
        for n in work:
            resolved[n] = self.resolve(self.defs[n], frozenset(), n)
        while self.pending:
            n, ast = self.pending.pop(0)
            self.globals.add(n)
            resolved[n] = self.resolve(ast, frozenset(), n)
            work.append(n)
        for n in work:
            out.append(self.compile_def(n, resolved[n]))
        return "\n".join(out) + "\n"


def compile_source(src, typecheck=True):
    return Compiler(src, typecheck).compile()


def compile_book(src, typecheck=True):
    return ir.parse_book(compile_source(src, typecheck))
