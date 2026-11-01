"""Step 25: the Ω-L peak-memory bound B as a function of the input size N (SPEC §7.3).

Step 24 computes B_nodes / B_vars for one concrete N by a counting run.  Here B(N) is derived in closed form.

Method.  An Ω-L program's recursions are structural or on a guarded numeric predecessor with constant offsets
(rule R), and every rule instance has a fixed node delta and var count, so when the work done for input N is
fixed by N alone (no data-dependent branch whose arm costs differ), B(N) is a C-finite sequence: it satisfies a
linear recurrence with constant coefficients (numeric recursion f(n) -> f(n-k1) .. f(n-km) gives the
characteristic factor x^K - sum x^(K-kj); a structural recursion over data built by such a recursion gives the
data size's recurrence; non-recursive work adds (x-1) factors).  So:

  1. count B(N) exactly for N = 0, 1, .. (eal.count_run, the same counting run as step 24);
  2. find the shortest linear recurrence of the sequence from a start N0 (Berlekamp–Massey over exact
     rationals), using only the first 2L + 2 terms after N0;
  3. solve it: rational roots of the characteristic polynomial with multiplicities give N^j r^N terms, the
     rest (x^2 - x - 1 for fib) a fundamental sequence U (U = Fibonacci there); coefficients solved exactly;
  4. *certify*: the closed form must equal the counted B(N) for every N of the range (held-out terms
     included), and its dominant root must not exceed what R allows (the largest numeric fan-out, 1 for a
     program without a numeric fan-out above 1).

When no short recurrence exists (data-dependent cost: insertion sort's comparisons) the fallback is an
*envelope*: the tightest upper bound sum c_j phi_j(N) in a basis chosen from the R class (polynomials of
growing degree, c^N for the numeric fan-outs), fitted on the first 2/3 of the range and checked on all of it.

Soundness is what was checked: B_sym(N) >= counted B(N) (exact: =) on every N of the stated range.  Beyond the
range an exact form rests on the recurrence argument above, an envelope on nothing but the trend.

usage:  python3 -m omega.eal --symbolic PROGRAM [NMAX]       (programs/*.olm, N substituted)
"""
import itertools, re, time
from fractions import Fraction as Fr
from . import eal, lang, progs

MUT = eal.MUT          # OMEGA_EAL_MUT 8, 9: symbolic mutants (tests/test_s25.py)


# ------------------------------------------------------------------------------------- sequences
def counted(src_of, Ns, budget=4.0, cap=400000, fuel=10**7):
    """[(N, B_nodes, B_vars)] for N in Ns, stopping when one run exceeds `budget` seconds or B exceeds cap."""
    out = []
    for N in Ns:
        t = time.time()
        r = eal.count_run(lang.compile_book(src_of(N)), fuel=fuel)
        out.append((N, r["B_nodes"], r["B_vars"]))
        if time.time() - t > budget or max(r["B_nodes"], r["B_vars"]) > cap: break
    return out


def berlekamp_massey(s):
    """Shortest c (list of Fractions) with s[n] = sum_i c[i] * s[n-1-i] for all n >= len(c) in s."""
    s = [Fr(x) for x in s]
    C, B = [Fr(1)], [Fr(1)]
    L, m, b = 0, 1, Fr(1)
    for n in range(len(s)):
        d = s[n] + sum(C[i] * s[n - i] for i in range(1, L + 1))
        if d == 0:
            m += 1; continue
        T = C[:]
        coef = d / b
        C = C + [Fr(0)] * max(0, len(B) + m - len(C))
        for i, x in enumerate(B): C[i + m] -= coef * x
        if 2 * L <= n:
            L, B, b, m = n + 1 - L, T, d, 1
        else:
            m += 1
    C = C + [Fr(0)] * (L + 1 - len(C))
    return [-x for x in C[1:L + 1]]


# ---------------------------------------------------------------------------- polynomial helpers
def pdiv_root(p, r):
    """p (coefficients highest first) divided by (x - r); returns (quotient, remainder)."""
    q, acc = [], Fr(0)
    for a in p:
        acc = acc * r + a; q.append(acc)
    return q[:-1], q[-1]


def divisors(n):
    n = abs(n)
    return [d for d in range(1, n + 1) if n % d == 0] if n else [1]


def rational_roots(p):
    """Rational roots of p (Fractions, highest first) with multiplicities, and the rest of p."""
    roots = {}
    while len(p) > 1 and p[-1] == 0:
        roots[Fr(0)] = roots.get(Fr(0), 0) + 1; p = p[:-1]
    den = 1
    for a in p: den = den * a.denominator // __import__("math").gcd(den, a.denominator)
    ip = [int(a * den) for a in p]
    cands = sorted({Fr(s * a, b) for a in divisors(ip[-1]) for b in divisors(ip[0]) for s in (1, -1)}, key=lambda x: (abs(x), x))
    for r in cands:
        while len(p) > 1:
            q, rem = pdiv_root(p, r)
            if rem != 0: break
            roots[r] = roots.get(r, 0) + 1; p = q
    return roots, p


def fundamental(rest, n):
    """U(0..n) for the monic recurrence with characteristic polynomial `rest` (highest first): U(0..d-2) = 0, U(d-1) = 1."""
    d = len(rest) - 1
    c = [-a / rest[0] for a in rest[1:]]
    u = [Fr(0)] * (d - 1) + [Fr(1)]
    while len(u) <= n + d: u.append(sum(c[i] * u[-1 - i] for i in range(d)))
    return u


def solve(A, y):
    """Exact Gaussian elimination; A square.  None if singular."""
    n = len(A)
    M = [list(map(Fr, A[i])) + [Fr(y[i])] for i in range(n)]
    for col in range(n):
        piv = next((r for r in range(col, n) if M[r][col] != 0), None)
        if piv is None: return None
        M[col], M[piv] = M[piv], M[col]
        for r in range(n):
            if r != col and M[r][col] != 0:
                f = M[r][col] / M[col][col]
                M[r] = [a - f * b for a, b in zip(M[r], M[col])]
    return [M[i][n] / M[i][i] for i in range(n)]


# --------------------------------------------------------------------------------- closed forms
class Closed:
    """sum over terms coef * N^j * r^N  +  sum_i coef_i * U(N + i) (U: fundamental sequence of `rest`), for N >= start."""
    def __init__(self, terms, ucoef, rest, start, exact=True, basis=None):
        self.terms, self.ucoef, self.rest, self.start, self.exact = terms, ucoef, rest, start, exact
        self.basis = basis

    def __call__(self, N):
        v = sum(c * Fr(N) ** j * Fr(r) ** N for c, j, r in self.terms)
        if self.ucoef:
            u = fundamental(self.rest, N + len(self.ucoef))
            v += sum(c * u[N + i] for i, c in enumerate(self.ucoef))
        return v

    def dominant(self):
        rs = [abs(float(r)) for c, j, r in self.terms if c != 0]
        if self.ucoef and any(self.ucoef):
            u = fundamental(self.rest, 400)        # dominant root modulus of the irrational part (reported only)
            rs += [abs(float(u[400] / u[399])) if u[399] else 0.0]
        return max(rs) if rs else 0.0

    def text(self, var="N"):
        parts = []
        if self.ucoef:
            uname = "F" if self.rest == [1, -1, -1] else "U"
            for i, c in enumerate(self.ucoef):
                if c != 0: parts.append((c, f"{uname}({var}{'+' + str(i) if i else ''})"))
        for c, j, r in sorted(self.terms, key=lambda t: (-abs(float(t[2])), -t[1])):
            if c == 0: continue
            f = ("" if j == 0 else (var if j == 1 else f"{var}^{j}"))
            e = "" if r == 1 else (f"{fmt_num(r)}^{var}" if r > 0 else f"({fmt_num(r)})^{var}")
            fac = "·".join(x for x in (f, e) if x)
            parts.append((c, fac))
        s = ""
        for c, fac in parts:
            sign = "-" if c < 0 else "+"
            mag = abs(c)
            body = fmt_num(mag) if not fac else (fac if mag == 1 else f"{fmt_num(mag)}·{fac}")
            s += f" {sign} {body}" if s else ("-" + body if c < 0 else body)
        return s or "0"

    def legend(self):
        if not self.ucoef: return ""
        if self.rest == [1, -1, -1]: return "F = Fibonacci (F(0) = 0, F(1) = 1)"
        d = len(self.rest) - 1
        return f"U: U(0..{d - 2}) = 0, U({d - 1}) = 1, characteristic polynomial {poly_text(self.rest)}"


def fmt_num(x):
    x = Fr(x)
    return str(x.numerator) if x.denominator == 1 else f"{x.numerator}/{x.denominator}"


def poly_text(p):
    d = len(p) - 1
    out = []
    for i, a in enumerate(p):
        if a == 0: continue
        k = d - i
        m = "" if (abs(a) == 1 and k) else fmt_num(abs(a))
        t = m + ("x" if k == 1 else f"x^{k}" if k else "")
        out.append(("- " if a < 0 else "+ ") + t)
    return " ".join(out).lstrip("+ ")


def closed_from_recurrence(seq, start, c):
    """Closed form of seq[start:] given s[n] = sum c[i] s[n-1-i] (n >= start + len(c))."""
    L = len(c)
    char = [Fr(1)] + [-x for x in c]
    roots, rest = rational_roots(char)
    shift = roots.pop(Fr(0), 0)                  # x^k factor: recurrence holds k terms later
    start += shift
    basis = [(j, r) for r, m in roots.items() for j in range(m)]
    nu = len(rest) - 1
    nb = len(basis) + nu
    if nb == 0: return None
    pts = list(range(start, start + nb))
    if pts[-1] >= len(seq): return None
    if nu:
        u = fundamental(rest, pts[-1] + nu)
    A = [[Fr(N) ** j * r ** N for j, r in basis] + ([u[N + i] for i in range(nu)] if nu else []) for N in pts]
    x = solve(A, [seq[N] for N in pts])
    if x is None: return None
    terms = [(x[k], j, r) for k, (j, r) in enumerate(basis)]
    return Closed(terms, x[len(basis):], rest if nu else None, start)


def find_exact(seq, max_start=4, margin=4):
    """Shortest recurrence over all start points <= max_start (each fitted on 2L + 2 terms, held-out terms after
    that), returned as a certified Closed or None."""
    best = None
    for st in range(0, max_start + 1):
        s = seq[st:]
        if len(s) < 6: break
        for L in range(1, (len(s) - margin) // 2 + 1):
            c = berlekamp_massey(s[:2 * L + 2])
            if len(c) > L: continue
            cf = closed_from_recurrence(seq, st, c)
            if cf is None: continue
            if MUT == 8 or all(cf(N) == seq[N] for N in range(cf.start, len(seq))):   # mutant 8: no held-out check
                if best is None or len(c) + cf.start < len(best[0]) + best[1].start: best = (c, cf)
                break
    return best[1] if best else None


# ------------------------------------------------------------------------------------- envelopes
def envelope(seq, bases, fit_frac=2 / 3):
    """Tightest upper envelope sum a_j phi_j(N) >= seq[N] (min sum of gaps) on the fit range, by vertex
    enumeration (an LP optimum touches k points); checked on the whole range.  Returns a Closed or None."""
    n = len(seq)
    nfit = max(4, int(n * fit_frac))
    found = []
    for name, basis in bases:
        k = len(basis)
        phi = [[Fr(N) ** j * r ** N for j, r in basis] for N in range(n)]
        colsum = [sum(phi[N][i] for N in range(nfit)) for i in range(k)]
        # candidate touching points: the points on the upper hull side; trying all k-subsets of the fit range
        # is exact but slow, so only points that are not strictly dominated by the chord of their neighbours
        cand = [N for N in range(nfit) if N in (0, nfit - 1) or 2 * seq[N] >= seq[N - 1] + seq[N + 1] or k > 2]
        if len(cand) > 22:                                  # keep it cheap: the largest local excesses
            step = len(cand) / 22
            cand = sorted({cand[int(i * step)] for i in range(22)} | {cand[0], cand[-1]})
        best = None
        for pts in itertools.combinations(cand, k):
            x = solve([phi[N] for N in pts], [seq[N] for N in pts])
            if x is None or x[-1] < 0: continue                # a negative leading term would eventually go below 0
            g = sum(a * c for a, c in zip(x, colsum)) - sum(seq[:nfit])
            if best is not None and g >= best[0]: continue
            if MUT != 9 and any(sum(a * p for a, p in zip(x, phi[N])) < seq[N] for N in range(nfit)): continue
            best = (g, x)
        if best is None: continue
        cf = Closed([(a, j, r) for a, (j, r) in zip(best[1], basis)], [], None, 0, exact=False, basis=name)
        cf.heldout = nfit < n
        if MUT == 9 or all(cf(N) >= seq[N] for N in range(n)): found.append((sum(cf(N) - seq[N] for N in range(n)), len(found), cf))
    return min(found)[2] if found else None          # the tightest basis that holds on the whole range


def r_bases(rep):
    """Envelope bases allowed by the R class of the program: polynomials up to degree 3, then c^N (c the numeric fan-outs)."""
    fan = sorted({f for (_, kind, f) in rep["recursion"].values() if kind == "numeric" and f > 1})
    out = [(f"degree {d}", [(j, Fr(1)) for j in range(d + 1)]) for d in (1, 2, 3)]
    for c in fan: out.append((f"{c}^N", [(0, Fr(1)), (1, Fr(1)), (0, Fr(c))]))
    return out


# ---------------------------------------------------------------------------------- the analysis
def r_limit(rep):
    """Largest growth rate R allows: the largest numeric fan-out (> 1), else 1 (polynomial)."""
    fan = [f for (_, kind, f) in rep["recursion"].values() if kind == "numeric"]
    return max([1] + fan)


def analyse(src_of, Nmax=None, budget=4.0):
    """src_of(N) -> source.  Returns a dict with the closed forms, the certified range and tightness."""
    rep = eal.check(src_of(3))
    if not rep["ok"]: return {"ok": False, "reason": rep["reason"]}
    Ns = range(0, (Nmax or 60) + 1)
    data = counted(src_of, Ns, budget)
    out = {"ok": True, "range": (data[0][0], data[-1][0]), "R": eal.growth(rep["recursion"]), "r_limit": r_limit(rep),
           "counted": data}
    for k, key in ((1, "nodes"), (2, "vars")):
        seq = [d[k] for d in data]
        cf = find_exact(seq)
        if cf is not None and cf.dominant() > r_limit(rep) + 1e-9:
            cf = None                         # faster than R allows: not trusted
        if cf is None:                        # data-dependent: envelope checked on held-out N, else fitted on all of them
            cf = envelope(seq, r_bases(rep)) or envelope(seq, r_bases(rep), 1.0)
        if cf is None:
            out[key] = None; continue
        lo = cf.start if cf.exact else 0
        vals = [(N, cf(N), seq[N]) for N in range(len(seq))]
        sound = all(v >= s for N, v, s in vals if N >= lo)
        ratios = [float(v / s) for N, v, s in vals if N >= lo and s]
        out[key] = {"closed": cf, "formula": cf.text(), "legend": cf.legend(), "exact": cf.exact, "start": lo,
                    "table": {N: s for N, _, s in vals if N < lo}, "sound": sound,
                    "max_ratio": max(ratios), "mean_ratio": sum(ratios) / len(ratios), "basis": cf.basis,
                    "dominant": cf.dominant(), "heldout": getattr(cf, "heldout", True)}
    return out


def evaluate(res, key, N):
    """B_key(N) from the closed form (the table below its start), as an int (ceiling)."""
    r = res[key]
    if N in r["table"]: return r["table"][N]
    v = r["closed"](N)
    return -((-v.numerator) // v.denominator)


def report(label, res):
    lines = []
    if not res["ok"]:
        return f"{label}: not in Ω-L: {res['reason']}"
    lines.append(f"{label}: Ω-L, symbolic bound in N (counted and certified on N = {res['range'][0]}..{res['range'][1]})")
    for f, g in res["R"].items(): lines.append(f"  recursion {f}: {g}")
    for key in ("nodes", "vars"):
        r = res[key]
        if r is None:
            lines.append(f"  B_{key}(N): no closed form or envelope found (use the per-N counting bound)"); continue
        kind = "exact" if r["exact"] else (f"upper envelope ({r['basis']}, " +
                                           ("fitted on 2/3 of the range, held out on the rest)" if r["heldout"] else
                                            "fitted on the whole range: no claim beyond it)"))
        cond = f" for N >= {r['start']}" if r["start"] else ""
        lines.append(f"  B_{key}(N) = {r['formula']}{cond}   [{kind}]")
        if r["table"]: lines.append(f"    below: {', '.join(f'B({N}) = {v}' for N, v in r['table'].items())}")
        if r["legend"]: lines.append(f"    {r['legend']}")
        lines.append(f"    growth {r['dominant']:.4g}^N (R allows <= {res['r_limit']}^N); "
                     f"B_sym / counted: max {r['max_ratio']:.3f}, mean {r['mean_ratio']:.3f}; sound on the range: {r['sound']}")
    return "\n".join(lines)


def program_src(name):
    return lambda N: progs.source(name, N)


def file_src(path):
    text = open(path).read()
    return lambda N: re.sub(r"\bN\b", str(N), text)


def main(argv):
    import os
    name = argv[0]
    nmax = int(argv[1]) if len(argv) > 1 else None
    src_of = file_src(name) if os.path.exists(name) else program_src(name)
    res = analyse(src_of, nmax)
    print(report(name, res))
    return 0 if res["ok"] and all(res[k] and res[k]["sound"] for k in ("nodes", "vars")) else 1
