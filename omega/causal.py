"""Causal bounds W over all schedules (step 24's results/s24/worst.py as a library, step 25 adds vars).

Every interaction e has a node delta w(e) and causes: the events that created its two nodes and the events whose
links built the wire that made the pair active.  The interactions done after any schedule prefix form a causally
closed set, so the live node count is n0 + sum of w over a closed set and

    W_nodes = n0 + max-weight closure of the event DAG            (min cut, Picard 1976)

bounds the peak of every schedule (SPEC §7.2).  Step 25, vars: event e allocates a(e) vars; var v is freed by the
second arrival at it, i.e. once every event of F_v (the events whose links reach v's two ends, through
substitution chains) has happened.  When F_v has a causal maximum m_v (all of F_v are ancestors of m_v), "v is
freed" = "m_v is in the prefix", so

    W_vars = v0 + max closure of a(e) - #{v : m_v = e}

(vars whose F_v has no causal maximum are counted as never freed, which only raises W).  This holds for an
implementation whose links are atomic (the semantic reducer).  The fabric and the RTL free a var when a LINK
*message* arrives, which can be any number of cycles after the interaction that sent it, so W_vars is not a bound
there; admission control (omega/admission.py) uses W_nodes and B_vars."""
import collections, sys
from . import semantic, eal
from .ports import *


class DNet(semantic.Net):
    def __init__(self, book, track_vars=True):
        super().__init__(book)
        self.cur = 0; self.w = [0]; self.a = [0]; self.deps = [set()]
        self.writer = {}; self.rdeps = {}; self.creator = {}
        self.track_vars = track_vars
        self.freeset = []                 # F_v of every freed var

    def alloc_node(self, a1, a2, o=0):
        n = super().alloc_node(a1, a2, o); self.creator[n] = self.cur; return n

    def alloc_var(self, o=0):
        self.a[self.cur] += 1
        return super().alloc_var(o)

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
            if self.track_vars: self.freeset.append(deps)
            del self.vars[v]; del self.vown[v]
            a = old

    def interact(self, a, b):
        d = set(self.rdeps.pop((a, b), set()) or self.rdeps.pop((b, a), set()))
        for p in (a, b):
            if tag(p) in NODE_TAGS: d.add(self.creator.get(payload(p), 0))
        self.cur = len(self.w); self.w.append(0); self.a.append(0); self.deps.append(d)
        n0 = len(self.nodes); super().interact(a, b); self.w[self.cur] = len(self.nodes) - n0


def maxclosure(w, deps):
    """Max-weight closure via Dinic min cut.  Event 0 (the initial load) is forced in."""
    n = len(w); S, T = n, n + 1
    INF = 1 << 60
    g = [[] for _ in range(n + 2)]

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

        def dfs():
            stack, path = [(S, INF)], []
            while True:
                u, f = stack[-1]
                if u == T:
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
            f = dfs()
            if not f: break
            flow += f
    return pos - flow


def ancestors(deps, limit=40000):
    """Ancestor bitsets (Python ints) in event order; None when the DAG is too large."""
    if len(deps) > limit: return None
    anc = []
    for e, ds in enumerate(deps):
        m = 0
        for d in ds:
            if d != e: m |= anc[d] | (1 << d)
        anc.append(m)
    return anc


def bound(book, fuel=10**8, with_vars=True, order="lifo"):
    """{"W_nodes", "W_vars" (None if the DAG is too large for the var analysis), "events", "freed_exact"}."""
    net = DNet(book, track_vars=with_vars)
    root = net.alloc_var()
    net.cur = 0
    net.instantiate(book.id("main"), mk(VAR, 0, root))
    n0, v0 = len(net.nodes), len(net.vars)
    net.a[0] = 0                                   # the initial load is counted in v0
    net.normalize(None, fuel, order)
    out = {"W_nodes": n0 + maxclosure(net.w, net.deps), "events": len(net.w), "readback": semantic.readback_net(net, root),
           "W_vars": None, "freed_exact": None}
    if with_vars:
        anc = ancestors(net.deps)
        if anc is not None:
            wv = list(net.a); wv[0] = 0
            exact = 0
            for F in net.freeset:
                m = max(F) if eal.MUT != 10 else min(F)      # mutant 10: a var counted as freed by the first of its events
                if m == 0: continue                    # freed during the load: already outside v0
                need = 0
                for e in F:
                    if e != m: need |= 1 << e
                if need & ~anc[m] == 0 or eal.MUT == 10:
                    wv[m] -= 1; exact += 1
            out["W_vars"] = v0 + maxclosure(wv, net.deps)
            out["freed_exact"] = (exact, len(net.freeset))
    return out


if __name__ == "__main__":
    from . import progs, eal
    sys.setrecursionlimit(100000)
    for spec in sys.argv[1:]:
        name, N = spec.split(":"); N = int(N)
        book = progs.book(name, N)
        w = bound(book); b = eal.bound(book)
        print(f"{name}({N}): W_nodes {w['W_nodes']} (B {b['B_nodes']}), W_vars {w['W_vars']} (B {b['B_vars']}), "
              f"frees with a causal maximum {w['freed_exact']}", flush=True)
