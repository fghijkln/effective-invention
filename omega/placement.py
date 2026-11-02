"""Step 29: a placement-aware memory certificate for a W x H mesh (SPEC §7.8).

Step 28 (§7.7) certifies a job on a mesh only if *every* cell has room for the whole job (slots_mesh = max(B) +
D_max + reserve), because the admission rule assumes nothing about where the work goes.  That rule does not get
smaller on a bigger mesh.  This module certifies a job (or a set of admitted jobs) from the *total* live load and
the mesh's placement policy instead:

    Lemma (pigeonhole).  Let the live load of the mesh be at most L_n nodes and L_v vars (§7.2 / §7.3 bounds:
    L_n = W_nodes or B_nodes, L_v = B_vars, summed over the running jobs, plus nothing else).  Cell d starts with
    f_n(d) / f_v(d) free slots (after ballast, other tenants, the root pool).  Call d *node-poor* when it has fewer
    than T = lm_hi free node slots; that takes at least c_n(d) = max(0, f_n(d) - T + 1) live nodes in d (var-poor
    alike).  If for every cell c the cells of its ball Ball(c, r) (Manhattan radius r = rgrad) cannot all be made
    poor, i.e. there is no split of Ball(c, r) into P_n, P_v with  sum_{P_n} c_n <= L_n  and  sum_{P_v} c_v <= L_v,
    then at every moment of every schedule every cell has, within r hops, a cell with >= T free node AND var
    slots, i.e. a cell whose `roomy` bit is set (low-memory mode, lm_hi = T).

    Homogeneous cells (f = S everywhere, m = S - T + 1):   floor(L_n / m) + floor(L_v / m) <= n_r - 1,
    n_r = the smallest ball (|Ball(c, r)| at a corner; the whole mesh when r >= W + H - 2).

Why this is enough for progress (an argument, as §7.1, not a machine-checked proof): with a roomy cell within
`rgrad` hops of every cell, every cell has rdist < rgrad + 1, so every non-roomy cell has a downhill neighbour
(§5, step 19): a SPAWN that does not fit is forwarded downhill at once (rule a), an escalated SWI / commutation goes
downhill (rule b), a NODE / PULL that blocks the ejection head of a full cell is passed on (rule d), and a roomy
cell (rdist 0, no downhill neighbour, no reserve) takes any expansion: it has >= lm_lo >= D_max free slots.  The
gradient only changes when free counts change, which happens only through rule instances (expansions,
commutations, frees) and the migrations that belong to one redex; Ω-L jobs terminate, so there are finitely many.
Between two changes the gradient is fixed and every pending SPAWN reaches room within rgrad hops (the §7.1 (2)
walk, now with no cell beyond the gradient).  The rotor-router part of §7.1 (2) is not needed.

What is *not* claimed: a per-cell peak bound.  The policy lets any one cell fill up to its slots (a cell may do
almost all the work), so the per-cell peak is bounded only by S; what the certificate bounds is the room the mesh
always keeps somewhere near every cell.  Not covered (as in §7.2): the task stack, cycle limits, untyped jobs,
lm_mode != 2, lm_lo < D_max, rgrad = 0.

Checker mutants (OMEGA_S29_MUT, tests/test_s29.py --mutants) break this rule one way each.
"""
import itertools, os
from . import fabric

MUT = int(os.environ.get("OMEGA_S29_MUT", "0"))


def cells(W, H):
    return [(x, y) for y in range(H) for x in range(W)]


_BALLS = {}


def ball(W, H, c, r):
    k = (W, H, c, r, MUT)
    if k not in _BALLS: _BALLS[k] = _ball(W, H, c, r)
    return _BALLS[k]


def _ball(W, H, c, r):
    if MUT == 3: r = W + H                                   # mutant 3: ignores rgrad (every cell sees the whole mesh)
    if MUT == 6: r = r + 1                                   # mutant 6: ball one hop too wide
    x, y = c
    return [(u, v) for (u, v) in cells(W, H) if abs(u - x) + abs(v - y) <= r]


def min_ball(W, H, r):
    return min(len(ball(W, H, c, r)) for c in cells(W, H))


def poor_cost(f, T):
    """Live slots it takes to make a cell with f free slots have fewer than T free."""
    if MUT == 1: T = 0                                       # mutant 1: ignores the watermark (poor = full)
    if MUT == 5: return max(0, f - T + 2)                    # mutant 5: off by one (fewer than T - 1 free)
    return max(0, f - T + 1)


def _ball_coverable(cn, cv, Ln, Lv):
    """Can the adversary make every cell of the ball poor?  cn / cv: per-cell costs.  Exact (2^|ball| splits)."""
    n = len(cn)
    if MUT == 2:                                             # mutant 2: nodes and vars separately (one resource poor everywhere)
        return sum(cn) <= Ln or sum(cv) <= Lv
    if all(a == cn[0] for a in cn) and all(b == cv[0] for b in cv):   # homogeneous: closed form
        a, b = cn[0], cv[0]
        qn = n if a == 0 else min(n, Ln // a)
        qv = n if b == 0 else min(n, Lv // b)
        return qn + qv >= n
    best = None
    for mask in range(1 << n):                               # mask bit i: cell i made var-poor, else node-poor
        sv = sum(cv[i] for i in range(n) if mask >> i & 1)
        if sv > Lv: continue
        sn = sum(cn[i] for i in range(n) if not mask >> i & 1)
        if sn <= Ln: return True
    return False


def certify(W, H, Ln, Lv, free_n=None, free_v=None, S=None, T=None, r=None, lm_lo=None, dmax=12, lm_mode=None):
    """True if the lemma above holds for a mesh with total live load <= (Ln, Lv).  free_n / free_v: dict cell ->
    free slots at the start (default S everywhere).  T = lm_hi, r = rgrad (defaults: fabric.LM_HI / RGRAD)."""
    T = fabric.LM_HI if T is None else T
    r = fabric.RGRAD if r is None else r
    lm_lo = fabric.LM_LO if lm_lo is None else lm_lo
    lm_mode = fabric.LM if lm_mode is None else lm_mode
    if W * H == 1 or r == 0 or lm_mode != 2: return False    # placement certificate: meshes in low-memory mode only
    if MUT != 4 and lm_lo < dmax: return False                # a roomy cell must fit every template (mutant 4: skips this)
    if MUT == 7 and S is not None: free_n = free_v = None     # mutant 7: ignores ballast / other tenants (assumes S free)
    cs = cells(W, H)
    if free_n is None and free_v is None:                     # homogeneous: one check per distinct ball size
        for n in sorted({len(ball(W, H, c, r)) for c in cs}):
            if _ball_coverable([poor_cost(S, T)] * n, [poor_cost(S, T)] * n, Ln, Lv): return False
        return True
    fn = free_n or {c: S for c in cs}
    fv = free_v or {c: S for c in cs}
    for c in cs:
        b = ball(W, H, c, r)
        if _ball_coverable([poor_cost(fn[d], T) for d in b], [poor_cost(fv[d], T) for d in b], Ln, Lv):
            return False
    return True


def certify_old(W, H, Ln, Lv, S, dmax=12):
    """Step 28 rule (§7.2 / §7.7): one cell S >= max(B); a mesh: every cell S >= max(B) + D_max + reserve."""
    need = max(Ln, Lv)
    return need <= S if W * H == 1 else need + dmax + max(fabric.LM_RSV, fabric.RSV) <= S


def certified(W, H, Ln, Lv, S, r=None, dmax=12):
    return certify_old(W, H, Ln, Lv, S, dmax) or certify(W, H, Ln, Lv, S=S, r=r, dmax=dmax)


def min_slots(W, H, Ln, Lv, r=None, dmax=12, cap=1 << 24):
    """Smallest homogeneous S that certifies (Ln, Lv) on W x H (step-28 rule or the placement certificate)."""
    lo, hi = 1, cap
    if not certified(W, H, Ln, Lv, hi, r, dmax): return None
    while lo < hi:                                            # both rules are monotone in S
        mid = (lo + hi) // 2
        if certified(W, H, Ln, Lv, mid, r, dmax): hi = mid
        else: lo = mid + 1
    return lo


def budgets(W, H, S, mix=(1, 1), T=None, r=None):
    """Per-resource admission budgets (bn, bv) for homogeneous S-slot cells such that any reservation sums
    Rn <= bn, Rv <= bv satisfy the certificate: with m = S - T + 1 and qn + qv = n_r - 1 (split in the ratio `mix`),
    bn = qn*m + m - 1 gives floor(Rn / m) <= qn.  Returns None if the mesh / mode gives no certificate."""
    T = fabric.LM_HI if T is None else T
    r = fabric.RGRAD if r is None else r
    if W * H == 1 or r == 0 or fabric.LM != 2: return None
    m = S - T + 1
    if m <= 0: return None
    nb = min_ball(W, H, r)
    tot = nb - 1
    a, b = max(mix[0], 0), max(mix[1], 0)
    qn = round(tot * a / (a + b)) if a + b else tot // 2
    qn = min(max(qn, 0), tot)
    qv = tot - qn
    if MUT == 8: qn, qv = qn + 1, qv + 1                     # mutant 8: budgets one cell too generous
    bn, bv = qn * m + m - 1, qv * m + m - 1
    assert MUT == 8 or certify(W, H, bn, bv, S=S, T=T, r=r) or bn == bv == m - 1
    return bn, bv


def witness(W, H, Ln, Lv, free_n=None, free_v=None, S=None, T=None, r=None):
    """Independent brute force (no closed form, no mutants): an occupancy of at most Ln job nodes and Lv job vars
    that leaves some ball with no cell having >= T free node and var slots, or None.  Returns {cell: (ln, lv)}."""
    T = fabric.LM_HI if T is None else T
    r = fabric.RGRAD if r is None else r
    cs = cells(W, H)
    fn = free_n or {c: S for c in cs}
    fv = free_v or {c: S for c in cs}
    for c in cs:
        x, y = c
        b = [(u, v) for (u, v) in cs if abs(u - x) + abs(v - y) <= r]
        for choice in itertools.product((0, 1), repeat=len(b)):
            occ = {}
            for d, k in zip(b, choice):
                occ[d] = (max(0, fn[d] - T + 1), 0) if k == 0 else (0, max(0, fv[d] - T + 1))
            if sum(o[0] for o in occ.values()) <= Ln and sum(o[1] for o in occ.values()) <= Lv:
                # check the witness itself: every cell of the ball has < T free nodes or < T free vars
                assert all(fn[d] - occ[d][0] < T or fv[d] - occ[d][1] < T for d in b)
                return occ
    return None


def job_load(book, bound="B"):
    """(L_n, L_v) for one Ω-L job: (B_nodes, B_vars) or, with bound="W", (W_nodes, B_vars) (§7.4)."""
    from . import eal, causal
    b = eal.bound(book)
    if bound == "W":
        return causal.bound(book, with_vars=False)["W_nodes"], b["B_vars"], b
    return b["B_nodes"], b["B_vars"], b
