"""Step 25: sort's B(N) depends on the data.  Decompose the counted B_rnd(N) as
   a + b·N + c·I + d·nil   (I = insert steps that go on (x > h), nil = inserts that end at Nil)
by exact least squares on N = 1..NMAX, check that it is exact, and derive the bound over all inputs of length N:
   I <= N(N-1)/2, nil <= N  ->  B(N) <= a + b·N + c·N(N-1)/2 + max(d, 0)·N."""
import sys
sys.path[:0] = ['.']
from fractions import Fraction as Fr
from omega import eal, progs, symbolic


def data(N):
    xs, s = [], 42
    for _ in range(N):
        xs.append(s % 100); s = (s * 1103515245 + 12345) % 2147483648
    I = nil = 0
    srt = []
    for h in reversed(xs):                       # sort(Cons(h, t)) = insert(h, sort(t))
        k = 0
        while k < len(srt) and h > srt[k]: k += 1
        I += k; nil += k == len(srt); srt.insert(k, h)
    return I, nil


NMAX = int(sys.argv[1]) if len(sys.argv) > 1 else 45
rows = []
for N in range(1, NMAX + 1):
    b = eal.count_run(progs.book("sort", N))
    I, nil = data(N)
    rows.append((N, I, nil, b["B_nodes"], b["B_vars"]))
for k, key in ((3, "nodes"), (4, "vars")):
    X = [[1, r[0], r[1], r[2]] for r in rows]
    y = [r[k] for r in rows]
    XtX = [[sum(Fr(X[n][i]) * X[n][j] for n in range(len(X))) for j in range(4)] for i in range(4)]
    Xty = [sum(Fr(X[n][i]) * y[n] for n in range(len(X))) for i in range(4)]
    a, b, c, d = symbolic.solve(XtX, Xty)
    exact = all(a + b * r[0] + c * r[1] + d * r[2] == r[k] for r in rows)
    bound = lambda N: a + b * N + c * Fr(N * (N - 1), 2) + max(d, 0) * N
    ok = all(bound(r[0]) >= r[k] for r in rows)
    print(f"B_{key}(N) = {symbolic.fmt_num(a)} + {symbolic.fmt_num(b)}·N + {symbolic.fmt_num(c)}·I + {symbolic.fmt_num(d)}·nil   exact on N = 1..{NMAX}: {exact}")
    A2, A1, A0 = c / 2, b - c / 2 + max(d, 0), a
    print(f"  over all inputs of length N (I <= N(N-1)/2, nil <= N): B_{key}(N) <= {symbolic.fmt_num(A2)}·N^2 + {symbolic.fmt_num(A1)}·N + {symbolic.fmt_num(A0)}"
          f"   >= counted on 1..{NMAX}: {ok};  bound / counted max {max(float(bound(r[0]) / r[k]) for r in rows):.2f}, at N = {NMAX}: {float(bound(NMAX) / rows[-1][k]):.2f}")
