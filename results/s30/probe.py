import sys, time
sys.setrecursionlimit(100000)
from fractions import Fraction as Fr
from omega import causal, eal, progs, semantic
from omega.ports import *
def dag(book):
    net = causal.DNet(book, track_vars=False)
    root = net.alloc_var(); net.cur = 0
    net.instantiate(book.id("main"), mk(VAR, 0, root))
    n0, v0 = len(net.nodes), len(net.vars); net.a[0] = 0
    net.normalize(None, 10**8, "lifo")
    return n0, v0, net.w, net.a, net.deps
for spec in sys.argv[1:]:
    name, N = spec.split(":"); N = int(N); t=time.time()
    book = progs.book(name, N); b = eal.bound(book)
    n0, v0, w, a, deps = dag(book)
    res = {}
    for lam in (Fr(0), Fr(1,4), Fr(1,2), Fr(1), Fr(2), Fr(4)):
        # scale to integers: weight = lam*w + a, multiply by 4
        ww = [int(4*(lam*w[e] + a[e])) for e in range(len(w))]
        res[lam] = (4*(lam*n0 + v0) + causal.maxclosure(ww, deps)) / 4
    Wn = n0 + causal.maxclosure(w, deps)
    print(spec, "events", len(w), "B", b["B_nodes"], b["B_vars"], "Wn", Wn, {str(k): float(v) for k,v in res.items()}, f"{time.time()-t:.1f}s", flush=True)
