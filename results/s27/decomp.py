"""Step 27: qsort_l's B(N) depends on the data.  B = a + b·N + c·P + d·A + e·Z exactly, where for first-element-pivot
quicksort on the input xs: P = sum over pivots of the length of the list partitioned (len t), A = sum of len(l) (app
walks), Z = calls that hit fuel 0.  Fit by exact least squares on many inputs, check exactness, derive the worst case."""
import sys, re, random
sys.path[:0] = ['.']
from fractions import Fraction as Fr
from omega import eal, progs, symbolic, lang

def stats(xs, fuel):
    P = A = Z = 0
    def qs(n, xs):
        nonlocal P, A, Z
        if n == 0: Z += 1; return []
        if not xs: return []
        h, t = xs[0], xs[1:]
        l = [x for x in t if x < h]; r = [x for x in t if not x < h]
        P += len(t); A += len(l)
        return qs(n - 1, l) + [h] + qs(n - 1, r)
    out = qs(fuel, xs)
    assert out == sorted(xs)
    return P, A, Z

SRC = open("programs/qsort_l.olm").read()
def src_list(xs):
    lst = "Nil"
    for x in reversed(xs): lst = f"Cons({x}, {lst})"
    return SRC.replace("def main = check(qs(N, rnd(N, 42)), 1)", f"def main = check(qs({len(xs)}, {lst}), 1)")

def inputs(Nmax, per=3, seed=27):
    rng = random.Random(seed)
    for N in range(0, Nmax + 1):
        yield progs._rnd(N)
        yield list(range(N)); yield list(range(N, 0, -1)); yield [5] * N
        for _ in range(per): yield [rng.randrange(100) for _ in range(N)]

def fit(rows, k):
    X = [[1, r[0], r[1], r[2], r[3]] for r in rows]; y = [r[k] for r in rows]; m = 5
    XtX = [[sum(Fr(X[n][i]) * X[n][j] for n in range(len(X))) for j in range(m)] for i in range(m)]
    Xty = [sum(Fr(X[n][i]) * y[n] for n in range(len(X))) for i in range(m)]
    return symbolic.solve(XtX, Xty)

if __name__ == "__main__":
    Nmax = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    rows = []
    for xs in inputs(Nmax):
        b = eal.count_run(lang.compile_book(src_list(xs)))
        P, A, Z = stats(xs, len(xs))
        rows.append((len(xs), P, A, Z, b["B_nodes"], b["B_vars"]))
    for k, key in ((4, "nodes"), (5, "vars")):
        a, b, c, d, e = fit(rows, k)
        exact = all(a + b * r[0] + c * r[1] + d * r[2] + e * r[3] == r[k] for r in rows)
        print(key, [symbolic.fmt_num(v) for v in (a, b, c, d, e)], "exact on", len(rows), "inputs:", exact)
