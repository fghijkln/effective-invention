"""Step 24 tightness study: a causal bound W on the live node count over ALL schedules (semantic model).

Every interaction e has a node delta w(e) and causes: the events that created its two nodes and the events whose
links built the wire that made the pair active.  Live nodes after any schedule prefix = n0 + sum of w over a
causally closed event set, so  max over schedules of the peak <= W = n0 + max-weight closure of the event DAG (equal when the recorded causes are complete)
(min cut, Picard 1976).  Compared with B_nodes = n0 + sum of max(0, w) (eal.bound) and with the peaks the
depth-first (lifo) and breadth-first (fifo) orders reach.   usage: worst.py prog:N ..."""
import sys, collections
sys.path[:0] = ['.']
from omega import semantic, progs, eal
from omega.ports import *


class DNet(semantic.Net):
    def __init__(self, book):
        super().__init__(book); self.cur = 0; self.w = [0]; self.deps = [set()]; self.writer = {}; self.rdeps = {}; self.creator = {}

    def alloc_node(self, a1, a2, o=0):
        n = super().alloc_node(a1, a2, o); self.creator[n] = self.cur; return n

    def instantiate(self, did, x=None, o=0, patch=None):
        n0 = self.next_node
        r = super().instantiate(did, x, o, patch)
        for n in range(n0, n0 + len(self.book[did].nodes)): self.creator[n] = self.cur
        return r

    def link(self, a, b):
        deps = {self.cur}
        while True:
            if not is_var(a):
                if not is_var(b):
                    self.rdx.append((a, b)); self.rdeps[(a, b)] = deps; return
                a, b = b, a
            v = payload(a)
            old = self.vars[v]
            if tag(old) == NONE:
                self.vars[v] = b; self.writer[v] = deps; return
            deps = deps | self.writer.pop(v)
            del self.vars[v]; del self.vown[v]
            a = old

    def interact(self, a, b):
        d = set(self.rdeps.pop((a, b), set()) or self.rdeps.pop((b, a), set()))
        for p in (a, b):
            if tag(p) in NODE_TAGS: d.add(self.creator.get(payload(p), 0))
        self.cur = len(self.w); self.w.append(0); self.deps.append(d)
        n0 = len(self.nodes); super().interact(a, b); self.w[self.cur] = len(self.nodes) - n0


def maxclosure(w, deps):
    """Max-weight closure via Dinic min cut.  Node 0 is forced in (initial load)."""
    n = len(w); S, T = n, n + 1
    INF = 1 << 60
    g = [[] for _ in range(n + 2)]       # edges: [to, cap, rev]

    def add(u, v, c):
        g[u].append([v, c, len(g[v])]); g[v].append([u, 0, len(g[u]) - 1])
    pos = 0
    for e in range(n):
        if e == 0: add(S, 0, INF)
        elif w[e] > 0: add(S, e, w[e]); pos += w[e]
        elif w[e] < 0: add(e, T, -w[e])
        for d in deps[e]:
            if d != e: add(e, d, INF)
    flow = 0
    while True:
        lvl = [-1] * (n + 2); lvl[S] = 0; q = collections.deque([S])
        while q:
            u = q.popleft()
            for v, c, _ in g[u]:
                if c > 0 and lvl[v] < 0: lvl[v] = lvl[u] + 1; q.append(v)
        if lvl[T] < 0: break
        it = [0] * (n + 2)

        def dfs(u, f):
            stack = [(u, f)]
            # iterative augmenting path search
            path = []
            while True:
                u, f = stack[-1]
                if u == T:
                    # push f along path
                    for (uu, i) in path:
                        e = g[uu][i]; e[1] -= f; g[e[0]][e[2]][1] += f
                    return f
                advanced = False
                while it[u] < len(g[u]):
                    v, c, _ = g[u][it[u]]
                    if c > 0 and lvl[v] == lvl[u] + 1:
                        path.append((u, it[u])); stack.append((v, min(f, c))); advanced = True; break
                    it[u] += 1
                if not advanced:
                    if u == S: return 0
                    stack.pop(); uu, i = path.pop(); it[uu] += 1
        while True:
            f = dfs(S, INF)
            if not f: break
            flow += f
    return pos - flow


if __name__ == "__main__":
    sys.setrecursionlimit(100000)
    for spec in sys.argv[1:]:
        name, N = spec.split(":"); N = int(N)
        book = progs.book(name, N)
        net = DNet(book); root = net.alloc_var()
        net.instantiate(book.id("main"), mk(VAR, 0, root))
        n0 = len(net.nodes)
        net.normalize(None, 10**8, "lifo")
        assert semantic.readback_net(net, root) == progs.expected(name, N)
        wc = n0 + maxclosure(net.w, net.deps)
        b = eal.bound(book); fifo = eal.count_run(book, "fifo")
        print(f"{name}({N}): B_nodes {b['B_nodes']}  causal bound W {wc}  fifo peak {fifo['peak_nodes']}  lifo peak {b['peak_nodes']}  "
              f"B/W {b['B_nodes'] / wc:.2f}  W/lifo {wc / b['peak_nodes']:.1f}", flush=True)


def check_random(name, N, k=40):
    """Soundness check of the DAG: no random order may exceed the exact worst case."""
    book = progs.book(name, N)
    net = DNet(book); root = net.alloc_var(); net.instantiate(book.id("main"), mk(VAR, 0, root)); n0 = len(net.nodes)
    net.normalize(None, 10**8, "lifo")
    wc = n0 + maxclosure(net.w, net.deps)
    pk = max(eal.count_run(book, "random", s)["peak_nodes"] for s in range(k))
    return wc, pk


def greedy_peak(name, N):
    """Adversarial schedule: always fire a redex that grows the net (expansion, commutation, SWI > 0) before any
    that shrinks it.  A lower bound on the worst case, to show how close it can be reached."""
    book = progs.book(name, N)
    net = eal.CountNet(book); root = net.alloc_var(); net.instantiate(book.id("main"), mk(VAR, 0, root))

    def grows(a, b):
        ta, tb = tag(a), tag(b)
        if ta < tb: a, b, ta, tb = b, a, tb, ta
        if tb == REF: return ta not in (ERA, DUP)
        if ta == REF: return tb != ERA
        if tb in NODE_TAGS and ta in NODE_TAGS: return not (ta == tb and label(a) == label(b) and ta in (CON, DUP))
        return ta == SWI and tb == NUM and payload(b) != 0
    up, down = [], []
    net.peak_nodes = len(net.nodes)
    while net.rdx or up or down:
        for r in net.rdx: (up if grows(*r) else down).append(r)
        net.rdx = []
        a, b = up.pop() if up else down.pop()
        net.interact(a, b)
    assert semantic.readback_net(net, root) == progs.expected(name, N)
    return net.peak_nodes
