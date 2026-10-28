"""Text IR (HVM2 style) parser / printer and flat definition templates.

    @main = a & @fib ~ (#10 a)
    tree := *            eraser
          | #123         number atom
          | @name        reference to a global definition (REF)
          | name         variable (each name occurs exactly twice in a definition)
          | (a b)        CON
          | {a b} | {3 a b}       DUP with label 0 / label 3
          | $(+ a r) | $(+' a r)  OPR (s=0 / s=1): principal = operand, a = other operand, r = result
          | ?(a r)       SWI: principal = number, a = (zero_case succ_case), r = result
"""
import re
from .ports import *

TOK = re.compile(r"\s*(?:(//[^\n]*)|(\$\()|(\?\()|([(){}*=&~])|(#-?\d+)|(@[A-Za-z_][\w.]*)|(\d+)|([A-Za-z_][\w.]*)|(\S))")


class Tree:
    __slots__ = ("kind", "label", "a", "b", "name", "val")

    def __init__(self, kind, label=0, a=None, b=None, name=None, val=0):
        self.kind, self.label, self.a, self.b, self.name, self.val = kind, label, a, b, name, val


def tokenize(src):
    out = []
    pos = 0
    while pos < len(src):
        m = TOK.match(src, pos)
        if not m or m.end() == pos:
            break
        pos = m.end()
        if m.group(1):
            continue
        tok = next(g for g in m.groups()[1:] if g is not None)
        out.append(tok)
    return out


class Parser:
    def __init__(self, src):
        self.t = tokenize(src)
        self.i = 0

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else None

    def next(self):
        tok = self.peek()
        self.i += 1
        return tok

    def expect(self, s):
        tok = self.next()
        if tok != s:
            raise SyntaxError(f"expected {s!r}, got {tok!r} at token {self.i}")

    def tree(self):
        tok = self.next()
        if tok == "*":
            return Tree(ERA)
        if tok.startswith("#"):
            return Tree(NUM, val=int(tok[1:]) & M32)
        if tok.startswith("@"):
            return Tree(REF, name=tok[1:])
        if tok == "(":
            a = self.tree(); b = self.tree(); self.expect(")")
            return Tree(CON, 0, a, b)
        if tok == "{":
            lab = 0
            if self.peek() is not None and self.peek().isdigit():
                lab = int(self.next())
            a = self.tree(); b = self.tree(); self.expect("}")
            return Tree(DUP, lab, a, b)
        if tok == "$(":
            op = self.next()
            # operators are tokenised char-by-char by the generic rules; glue them back
            while self.peek() in ("=", "<", ">", "&", "|", "'") or (self.peek() and len(self.peek()) == 1 and self.peek() in "!<>=|^'"):
                op += self.next()
            s = 0
            if op.endswith("'"):
                s, op = 1, op[:-1]
            if op not in OP_ID:
                raise SyntaxError(f"bad operator {op!r}")
            a = self.tree(); b = self.tree(); self.expect(")")
            return Tree(OPR, OP_ID[op] | (s << 4), a, b)
        if tok == "?(":
            a = self.tree(); b = self.tree(); self.expect(")")
            return Tree(SWI, 0, a, b)
        if re.match(r"[A-Za-z_]", tok):
            return Tree(VAR, name=tok)
        raise SyntaxError(f"unexpected token {tok!r}")

    def book(self):
        defs = []
        while self.peek() is not None:
            tok = self.next()
            if not tok.startswith("@"):
                raise SyntaxError(f"expected @name, got {tok!r}")
            self.expect("=")
            root = self.tree()
            rdx = []
            while self.peek() == "&":
                self.next()
                a = self.tree(); self.expect("~"); b = self.tree()
                rdx.append((a, b))
            defs.append((tok[1:], root, rdx))
        return defs


class Def:
    """Flat template.  Template ports use the normal encoding with payload = local index:
    VAR -> local var index, node tags -> local node index, REF label = definition id."""

    def __init__(self, name):
        self.name = name
        self.nodes = []   # list of (tagport, aux1, aux2); tagport = mk(tag,label,index)
        self.nvars = 0
        self.root = None
        self.redexes = []


class Book:
    def __init__(self):
        self.defs = []
        self.ids = {}

    def __getitem__(self, k):
        return self.defs[self.ids[k] if isinstance(k, str) else k]

    def id(self, name):
        return self.ids[name]

    def to_text(self):
        return "\n".join(def_to_text(self, d) for d in self.defs) + "\n"


def parse_book(src):
    raw = Parser(src).book()
    book = Book()
    for i, (name, _, _) in enumerate(raw):
        if name in book.ids:
            raise SyntaxError(f"duplicate definition @{name}")
        book.ids[name] = i
    for name, root, rdx in raw:
        d = Def(name)
        names = {}
        counts = {}

        def flat(t):
            if t.kind == ERA: return ERA_P
            if t.kind == NUM: return num(t.val)
            if t.kind == REF:
                if t.name not in book.ids:
                    raise SyntaxError(f"unknown reference @{t.name} in @{name}")
                return mk(REF, book.ids[t.name])
            if t.kind == VAR:
                counts[t.name] = counts.get(t.name, 0) + 1
                if t.name not in names:
                    names[t.name] = d.nvars; d.nvars += 1
                return mk(VAR, 0, names[t.name])
            idx = len(d.nodes)
            d.nodes.append(None)
            a = flat(t.a); b = flat(t.b)
            p = mk(t.kind, t.label, idx)
            d.nodes[idx] = (p, a, b)
            return p

        d.root = flat(root)
        d.redexes = [(flat(a), flat(b)) for a, b in rdx]
        bad = [n for n, c in counts.items() if c != 2]
        if bad:
            raise SyntaxError(f"@{name}: variables must occur exactly twice: {bad}")
        book.defs.append(d)
    if "main" not in book.ids:
        raise SyntaxError("no @main")
    return book


def def_to_text(book, d):
    def show(p):
        t = tag(p)
        if t == ERA: return "*"
        if t == NUM: return f"#{payload(p)}"
        if t == REF: return "@" + book.defs[label(p)].name
        if t == VAR: return f"v{payload(p)}"
        _, a, b = d.nodes[payload(p)]
        if t == CON: return f"({show(a)} {show(b)})"
        if t == DUP: return f"{{{label(p)} {show(a)} {show(b)}}}" if label(p) else f"{{{show(a)} {show(b)}}}"
        if t == OPR:
            l = label(p)
            return f"$({OPS[l & 15]}{chr(39) if l >> 4 else ''} {show(a)} {show(b)})"
        if t == SWI: return f"?({show(a)} {show(b)})"
        raise ValueError(t)
    s = f"@{d.name} = {show(d.root)}"
    for a, b in d.redexes:
        s += f"\n  & {show(a)} ~ {show(b)}"
    return s
