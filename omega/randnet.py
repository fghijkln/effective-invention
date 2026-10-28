"""Random interaction-net generator for differential fuzzing.

Produces a random book: a DAG of definitions (def i only references defs j > i, so expansion
terminates) built from random trees over every node kind (CON, DUP with 3 labels, OPR with random
op / flip bit, SWI) and every atom (ERA, NUM, REF, variables).  Variable occurrences are paired at
random inside each definition.  Nets that do not normalise within the fuel budget are rejected by
the caller (interaction combinators are Turing complete, so some random nets diverge).
"""
import random
from . import ir


def gen_book_text(seed, ndefs=None, size=None):
    rng = random.Random(seed)
    ndefs = ndefs if ndefs is not None else rng.randint(1, 5)
    size = size if size is not None else rng.randint(3, 30)
    names = ["main"] + [f"d{i}" for i in range(1, ndefs)]
    out = []
    for di, name in enumerate(names):
        later = names[di + 1:]
        leaves = []          # positions that hold a variable placeholder
        budget = [rng.randint(1, size)]

        def tree(depth):
            r = rng.random()
            if depth > 0 and budget[0] > 0 and r < 0.55:
                budget[0] -= 1
                k = rng.random()
                a = tree(depth - 1); b = tree(depth - 1)
                if k < 0.30: return f"({a} {b})"
                if k < 0.50: return f"{{{rng.randint(0, 2)} {a} {b}}}"
                if k < 0.70:
                    op = rng.choice(["+", "-", "*", "/", "%", "==", "!=", "<", ">", "<=", ">=", "&", "|", "^", "<<", ">>"])
                    return f"$({op}{chr(39) if rng.random() < 0.3 else ''} {a} {b})"
                if k < 0.85: return f"?({a} {b})"
                return f"({a} {b})"
            r = rng.random()
            if r < 0.50:
                leaves.append(len(leaves)); return f"\0{len(leaves) - 1}\0"
            if r < 0.65: return "*"
            if r < 0.88: return f"#{rng.choice([0, 0, 1, 2, 3, 5, 7, 100, 4294967295, rng.randint(0, 50)])}"
            if later: return "@" + rng.choice(later)
            return f"#{rng.randint(0, 9)}"
        root = tree(rng.randint(1, 4))
        rdx = []
        for _ in range(rng.randint(0, 6)):
            rdx.append((tree(rng.randint(0, 3)), tree(rng.randint(0, 3))))
        if not rdx and rng.random() < 0.7:
            rdx.append((tree(2), tree(2)))
        # pair the variable placeholders
        ids = list(range(len(leaves)))
        rng.shuffle(ids)
        subst = {}
        for k in range(0, len(ids) - 1, 2):
            subst[ids[k]] = subst[ids[k + 1]] = f"v{k // 2}"
        if len(ids) % 2:
            subst[ids[-1]] = "*"

        def fill(s):
            parts = s.split("\0")
            return "".join(subst[int(p)] if i % 2 else p for i, p in enumerate(parts))
        text = f"@{name} = {fill(root)}"
        for a, b in rdx:
            fa, fb = fill(a), fill(b)
            if fa == fb and fa.startswith("v"):
                fb = "*"; fa = "*"
            text += f"\n  & {fa} ~ {fb}"
        out.append(text)
    return "\n".join(out) + "\n"


def gen_book(seed, **kw):
    return ir.parse_book(gen_book_text(seed, **kw))
