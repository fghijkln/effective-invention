"""Step 30: joint node + var loads, the task stack, and the certificate built on them (SPEC §7.9).

Step 29 (omega/placement.py, §7.8) certifies a mesh from per-resource loads (L_n, L_v) = (B_nodes, B_vars) and
leaves the task stack out.  This module adds three things.

1. Joint loads.  At every moment of every schedule the interactions done so far form a causally closed set X of
   the event DAG (omega/causal.py), and the live counts are

       n(X) = n0 + sum_{e in X} w(e)            (w: node delta; exact, a node in flight holds no slot)
       v(X) <= v0 + sum_{e in X} a(e)           (a: vars allocated; RTL frees are not tied to an event, §7.3)

   so the set of (nodes, vars) pairs any schedule can show lies under the convex hull of {(n(X), v(X))}.  For every
   lam >= 0,  lam * n + v <= Phi(lam) = lam * n0 + v0 + maxclosure(lam * w + a)   (one min cut each).  A ball can be
   made entirely non-roomy only by a split (s_n, s_v) of its poor costs (§7.8) with  lam * s_n + s_v <= Phi(lam)
   for every lam (plus s_n <= W_nodes = Phi(inf) and s_v <= B_vars = Phi(0)).  `certify` decides this exactly
   for a given finite set of lam (sound for any set; exact for the hull when the set contains its breakpoints).
   `hull` returns Phi on a grid and `attainer` the closed set X* of the max-node cut with its (n, v), the
   independent witness that the hull is the box [0, W_nodes] x [0, B_vars] (X* attains both maxima at once).

2. The task stack.  Every task-stack / fork-deque / retry-slot entry is a pending link of two port words (K_LINK,
   K_SPAWN, K_FWD all hold a pair).  Nets are linear: a node's principal port is held in exactly one place, a var
   in at most two (its two ends), and an atom pair holds neither.  An atom-atom entry turns into exactly one
   atom-atom interaction (void, REF~NUM / REF~REF expansion; retries move the same entry).  Hence at every moment

       #entries (all cells)  <=  n + 2 v + A,     A = number of atom-atom interactions of the run (schedule-free)

   and with the joint loads, Q = max over the hull of n + 2v + A = Phi-bound at weights (1, 2) + A.  No per-cell
   bound below the global one follows from the policy (an entry can name a node anywhere, and one cell can hold
   every pending link), so the certificate requires QDEPTH >= Q + 3 (a cycle pushes up to 3 entries).

3. The step-30 certificate: `certified(W, H, loads, S, qdepth)` = memory (the step-28 single-cell rule or the
   step-29 ball cover, both with the joint loads) and QDEPTH >= Q + 3.

Checker mutants (OMEGA_S30_MUT, tests/test_s30.py --mutants) break it one way each.
"""
import itertools, os, sys
from fractions import Fraction as Fr
from . import causal, eal, fabric, placement
from .ports import *

MUT = int(os.environ.get("OMEGA_S30_MUT", "0"))
LAMS = (Fr(0), Fr(1, 8), Fr(1, 4), Fr(1, 2), Fr(1), Fr(2), Fr(4), Fr(8))
PUSH = 3                                                   # entries one engine cycle can push (omega_cell, pn <= 3)


# ------------------------------------------------------------------------------------------------ event DAG
class _ADNet(causal.DNet):
    """causal.DNet that also counts atom-atom interactions."""
    def __init__(self, book):
        super().__init__(book, track_vars=False); self.atoms = 0

    def interact(self, a, b):
        if tag(a) <= NUM and tag(b) <= NUM: self.atoms += 1
        super().interact(a, b)


def dag(book, fuel=10**8):
    net = _ADNet(book)
    root = net.alloc_var(); net.cur = 0
    net.instantiate(book.id("main"), mk(VAR, 0, root))
    n0, v0 = len(net.nodes), len(net.vars); net.a[0] = 0
    net.normalize(None, fuel, "lifo")
    return {"n0": n0, "v0": v0, "w": net.w, "a": net.a, "deps": net.deps, "atoms": net.atoms,
            "readback": causal.semantic.readback_net(net, root)}


def phi(D, lam_n, lam_v=1):
    """max over closed sets X of lam_n * n(X) + lam_v * v(X) (Fractions allowed; lam_n = None: nodes only)."""
    if lam_n is None: return D["n0"] + causal.maxclosure(D["w"], D["deps"])
    lam_n, lam_v = Fr(lam_n), Fr(lam_v)
    den = lam_n.denominator * lam_v.denominator
    ww = [int(den * (lam_n * w + lam_v * a)) for w, a in zip(D["w"], D["a"])]
    ww[0] = 0
    return Fr(int(den * (lam_n * D["n0"] + lam_v * D["v0"])) + causal.maxclosure(ww, D["deps"]), den)


def loads(book, lams=LAMS):
    """Joint loads of one Ω-L job: W_nodes, B_vars, atoms A, the hull Phi(lam), the task-stack bound Q."""
    D = dag(book)
    Wn = phi(D, None)
    Bv = D["v0"] + sum(D["a"][1:])
    hull = [(lam, phi(D, lam)) for lam in lams]
    if MUT == 1: hull = [(lam, p - 1 - lam * Wn // 4) for lam, p in hull]  # mutant 1: hull cut below what X* attains
    qv = phi(D, 1, 2)                                                       # max n + 2v over closed sets
    A = D["atoms"] if MUT != 2 else 0                                       # mutant 2: atom pairs not counted
    Q = int(qv) + A + 1                                                     # + the root var's host reference
    if MUT == 3: Q = Wn + Bv + A + 1                                        # mutant 3: vars counted once (one end each)
    return {"W_nodes": Wn, "B_vars": Bv, "atoms": A, "hull": hull, "Q": Q, "events": len(D["w"]), "dag": D}


def attainer(D):
    """Witness for the hull: a closed set X* with (n, v)(X*).
    Computed independently of maxclosure by a plain fixpoint: start from all events (v = B_vars), repeatedly drop an
    event with its descendants when that raises the node count and drops no var allocation.  When the result has
    n = W_nodes, one closed set attains (W_nodes, B_vars) at once and the joint hull is the whole box."""
    n = len(D["w"]); kids = [[] for _ in range(n)]
    for e, ds in enumerate(D["deps"]):
        for d in ds:
            if d != e: kids[d].append(e)
    inX = [True] * n
    def desc(e):
        out, st = set(), [e]
        while st:
            u = st.pop()
            if u in out or not inX[u]: continue
            out.add(u); st.extend(kids[u])
        return out
    changed = True
    while changed:
        changed = False
        for e in range(n - 1, 0, -1):
            if not inX[e]: continue
            s = desc(e)
            if sum(D["w"][u] for u in s) < 0 and not any(D["a"][u] for u in s):   # raises n(X), keeps every var allocation
                for u in s: inX[u] = False
                changed = True
    for e in range(n):                                           # closed: every dep of a member is a member
        if inX[e]: assert all(inX[d] for d in D["deps"][e]), "attainer not closed"
    nX = D["n0"] + sum(D["w"][e] for e in range(n) if inX[e])
    vX = D["v0"] + sum(D["a"][e] for e in range(1, n) if inX[e])
    return nX, vX


# ------------------------------------------------------------------------------------------------ certificate
def _split_feasible(sn, sv, L):
    """Can one moment show >= sn nodes and >= sv vars?  L: {"W_nodes", "B_vars", "hull"} (hull may be empty)."""
    if MUT == 4:                                                 # mutant 4: off by one (a load exactly at the cap counted out)
        if sn >= L["W_nodes"] or sv >= L["B_vars"]: return False
    if sn > L["W_nodes"] or sv > L["B_vars"]: return False
    return all(lam * sn + sv <= p for lam, p in L.get("hull", ()))


def _ball_coverable(cn, cv, L):
    n = len(cn)
    if MUT == 5:                                                 # mutant 5: a cell counts poor only if nodes AND vars are short
        return _split_feasible(sum(cn), sum(cv), L)
    if all(a == cn[0] for a in cn) and all(b == cv[0] for b in cv):
        a, b = cn[0], cv[0]
        return any(_split_feasible(q * a, (n - q) * b, L) for q in range(n + 1))
    for mask in range(1 << n):
        sv = sum(cv[i] for i in range(n) if mask >> i & 1)
        sn = sum(cn[i] for i in range(n) if not mask >> i & 1)
        if _split_feasible(sn, sv, L): return True
    return False


def certify_mesh(W, H, L, S=None, free_n=None, free_v=None, T=None, r=None, lm_lo=None, dmax=12, lm_mode=None):
    """Step-29 ball cover with joint loads L (dict, engine margin already added).  Same conditions as placement.certify."""
    T = fabric.LM_HI if T is None else T
    r = fabric.RGRAD if r is None else r
    lm_lo = fabric.LM_LO if lm_lo is None else lm_lo
    lm_mode = fabric.LM if lm_mode is None else lm_mode
    if W * H == 1 or r == 0 or lm_mode != 2 or lm_lo < dmax: return False
    cs = placement.cells(W, H)
    rr = r + 1 if MUT == 6 else r                                # mutant 6: ball one hop too wide
    if free_n is None and free_v is None:
        for n in sorted({len(placement._ball(W, H, c, rr)) for c in cs}):
            if _ball_coverable([placement.poor_cost(S, T)] * n, [placement.poor_cost(S, T)] * n, L): return False
        return True
    fn = free_n or {c: S for c in cs}
    fv = free_v or {c: S for c in cs}
    for c in cs:
        b = placement._ball(W, H, c, rr)
        if _ball_coverable([placement.poor_cost(fn[d], T) for d in b], [placement.poor_cost(fv[d], T) for d in b], L):
            return False
    return True


ENG = 2                                                    # nodes one engine may hold consumed-but-not-freed mid-rule


def margin(L, W, H):
    """Loads as the RTL can show them on a W x H mesh: an interaction is not atomic there, so each engine may have
    allocated its new nodes before freeing the <= 2 it consumes; nodes get + ENG per cell (and the hull with them).
    Vars need nothing (allocation-only already), Q gets the same node margin."""
    c = ENG * W * H if MUT != 8 else 0                       # mutant 8: no engine margin
    if L.get("no_frees"): c = 0                              # a B_nodes box counts no frees at all: nothing to add
    out = dict(L)
    out["W_nodes"] = L["W_nodes"] + c
    out["hull"] = [(lam, p + lam * c) for lam, p in L.get("hull", ())]
    if L.get("Q") is not None: out["Q"] = L["Q"] + c
    return out


def stack_ok(L, qdepth):
    if MUT == 7: return True                                     # mutant 7: stack not checked
    return qdepth >= L["Q"] + PUSH


def memory_ok(W, H, L, S, r=None, dmax=12):
    L = margin(L, W, H)
    need = max(L["W_nodes"], L["B_vars"])
    if W * H == 1: return need <= S                              # step 28 single-cell rule, W_nodes for nodes
    if need + dmax + max(fabric.LM_RSV, fabric.RSV) <= S: return True   # step 28 mesh rule
    return certify_mesh(W, H, L, S=S, r=r, dmax=dmax)


def certified(W, H, L, S, qdepth, r=None, dmax=12):
    return memory_ok(W, H, L, S, r, dmax) and stack_ok(margin(L, W, H), qdepth)


def qdepth_needed(W, H, L):
    return margin(L, W, H)["Q"] + PUSH


def min_slots(W, H, L, r=None, dmax=12, cap=1 << 24):
    lo, hi = 1, cap
    if not memory_ok(W, H, L, hi, r, dmax): return None
    while lo < hi:
        mid = (lo + hi) // 2
        if memory_ok(W, H, L, mid, r, dmax): hi = mid
        else: lo = mid + 1
    return lo


def box(Ln, Lv, Q=0):
    """Loads given as a plain B box (B_nodes, B_vars: no frees counted, so no engine margin), no hull."""
    return {"W_nodes": Ln, "B_vars": Lv, "hull": [], "Q": Q, "no_frees": True}


# ------------------------------------------------------------------------------------------------ brute force
def downsets(D, limit=200000):
    """All closed sets of a small DAG (event 0 forced in), as (n, v) pairs.  Independent of maxclosure."""
    n = len(D["w"]); deps = [set(d) - {e} for e, d in enumerate(D["deps"])]
    out = set(); cnt = [0]
    def rec(i, X):
        cnt[0] += 1
        if cnt[0] > limit: raise OverflowError
        if i == n:
            out.add((D["n0"] + sum(D["w"][e] for e in X), D["v0"] + sum(D["a"][e] for e in X if e))); return
        if i == 0 or deps[i] <= X: rec(i + 1, X | {i})
        if i != 0: rec(i + 1, X)
    rec(0, frozenset())
    return out


def witness(W, H, pts, S, T=None, r=None):
    """Brute force: a ball and an achievable (n, v) point that make every cell of the ball poor, or None."""
    T = fabric.LM_HI if T is None else T
    r = fabric.RGRAD if r is None else r
    m = S - T + 1
    for c in placement.cells(W, H):
        x, y = c
        b = [(u, v) for (u, v) in placement.cells(W, H) if abs(u - x) + abs(v - y) <= r]
        for q in range(len(b) + 1):
            for (n, v) in pts:
                if q * m <= n and (len(b) - q) * m <= v: return c, q, (n, v)
    return None


if __name__ == "__main__":
    from . import progs
    sys.setrecursionlimit(100000)
    for spec in sys.argv[1:]:
        name, N = spec.split(":")
        L = loads(progs.book(name, int(N)))
        b = eal.bound(progs.book(name, int(N)))
        print(f"{spec}: B {b['B_nodes']}/{b['B_vars']} W_nodes {L['W_nodes']} atoms {L['atoms']} Q {L['Q']} events {L['events']} "
              f"hull {[(str(l), float(p)) for l, p in L['hull']]} attainer {attainer(L['dag'])}", flush=True)
