"""Program suite: source loader with parameter N and Python reference results."""
import os, re
from . import lang

HERE = os.path.join(os.path.dirname(__file__), "..", "programs")
M = 0xFFFFFFFF


def _rnd(n, s=42):
    out = []
    for _ in range(n):
        out.append(s % 100)
        s = (s * 1103515245 + 12345) % 2147483648
    return out


def _fib(n):
    a, b = 0, 1
    for _ in range(n): a, b = b, a + b
    return a


def _fact(n):
    r = 1
    for i in range(1, n + 1): r = (r * i) & M
    return r


def _check(xs):
    return sum((i + 1) * x for i, x in enumerate(xs)) & M


REF = {
    "fib": _fib,
    "sum": lambda n: n * (n + 1) // 2 & M,
    "fact": _fact,
    "list": lambda n: sum(x * x + 1 for x in range(1, n + 1)) & M,
    "treesum": lambda n: 2 ** n & M,
    "treesum_direct": lambda n: 2 ** n & M,
    "sort": lambda n: _check(sorted(_rnd(n))),
    "qsort": lambda n: _check(sorted(_rnd(n))),
    "higher": lambda n: (n * (n + 1) // 2 + 9 * n) & M,
}


def source(name, n):
    with open(os.path.join(HERE, name + ".olm")) as f:
        return re.sub(r"\bN\b", str(n), f.read())


def book(name, n):
    return lang.compile_book(source(name, n))


def expected(name, n):
    return f"#{REF[name](n)}"
