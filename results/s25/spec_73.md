### 7.3 B as a closed form in the input size, and a causal var bound (step 25, `omega/symbolic.py`, `omega/causal.py`)

§7.2 reads B off one counting run per concrete N. Step 25 derives **B_nodes(N)** and **B_vars(N)** in closed form.

**Why a closed form exists.** Every rule instance has a fixed node delta and var count (§7.2), so B(N) is a sum of
per-interaction constants over the interaction multiset of the program at size N. Rule R (§7.2) allows only
structural recursion and recursion on a guarded numeric predecessor `n - k` with constant k. When the work done for
N is fixed by N alone (no data-dependent branch whose arms cost differently), the number of unfoldings of every
definition is a C-finite sequence in N: a numeric recursion `f(n) -> f(n-k1) … f(n-km)` contributes the
characteristic factor x^K − Σ x^(K−kj) (fib: x² − x − 1; `tsum(p) + tsum(p)`: x − 2), a structural recursion over a
value built by such a recursion inherits that value's size sequence, and straight-line work adds factors (x − 1).
So B(N) satisfies a linear recurrence with constant coefficients whose dominant root R bounds: at most the largest
numeric fan-out of the program (1 when it has none).

**Derivation** (`symbolic.analyse`): (1) count B(N) exactly for N = 0, 1, … (the §7.2 counting run, until one run
takes 4 s or B passes 400,000); (2) find the shortest linear recurrence from a start N0 ≤ 4 by Berlekamp–Massey over
exact rationals, fitted on the first 2L + 2 terms only; (3) solve it: rational roots of the characteristic
polynomial (with multiplicity m: N^j r^N, j < m) and, for an irreducible rest, its fundamental sequence U (U = the
Fibonacci numbers F for x² − x − 1); coefficients by exact Gaussian elimination; (4) **certify**: the closed form
must equal the counted B(N) at every N of the range, the terms after the 2L + 2 fitted ones being held out, and its
dominant root must not exceed R's limit. Terms below N0 are given as a table (piecewise form).

**Data-dependent cost.** When no recurrence of length ≤ (range − 4) / 2 reproduces the sequence (sort: insertion
sort's comparisons depend on the pseudo-random data), the tool falls back to the tightest **upper envelope** in a
basis R allows (polynomials of degree 1–3, c^N for the numeric fan-outs; vertex enumeration of the LP "minimise the
total gap subject to envelope ≥ B(N)", non-negative leading coefficient), fitted on 2/3 of the range and checked on
the rest, or, if no basis survives that, fitted on the whole range (then no claim is made beyond it). For sort a
program-level argument gives a data-independent bound instead (README step 25): B(N) = a + b·N + c·I + d·nil
exactly (I: insert steps that go on, nil: inserts that end at Nil), and I ≤ N(N − 1)/2, nil ≤ N give the bound over
every input of length N.

**What is certified.** Exactly what was checked: B_sym(N) = counted B(N) (exact forms) or ≥ (envelopes) on every N of
the reported range, plus, in `tests/test_s25.py`, on 1–4 values of N past it that the fit never saw. Beyond the
range an exact form rests on the C-finite argument above (an argument, not a proof: it assumes the per-N work is
fixed by N), an envelope on nothing.

**Results (suite).** All exact except sort, from N = 0 (no table needed):

| program | B_nodes(N) | B_vars(N) | growth (R allows) | certified on N = |
|---|---|---|---|---|
| fib | 24·F(N+1) − 14 | 19·F(N+1) − 11 | φ^N (2^N) | 0..21 |
| sum, fact | 11·N + 7 | 8·N + 6 | linear (1) | 0..60 |
| list | 54·N + 27 | 56·N + 23 | linear (1) | 0..60 |
| higher | 43·N + 42 | 44·N + 43 | linear (1) | 0..60 |
| treesum | 37·2^N − 23 | 32·2^N − 19 | 2^N (2^N) | 0..13 |
| treesum_direct | 12·2^N − 8 | 9·2^N − 5 | 2^N (2^N) | 0..15 |
| sort (descending input, worst case) | 29/2·N² + 97/2·N + 24 | 27/2·N² + 85/2·N + 20 | N² | 0..45 |
| sort (ascending input) | 84·N + 3 (N ≥ 1) | 74·N + 2 (N ≥ 1) | linear | 0..45 |
| sort (its own pseudo-random input), any input of length N | ≤ 29/2·N² + 139/2·N + 24 | ≤ 27/2·N² + 121/2·N + 20 | N² | decomposition exact on 1..45 |

**Causal var bound W_vars** (`causal.bound`). Event e allocates a(e) vars; var v is freed by the second arrival at
it, i.e. once every event of F_v (the events whose links reach its two ends, through substitution chains) has
happened. When F_v has a causal maximum m_v, "v freed" = "m_v done", so W_vars = v0 + max closure of
a(e) − #{v : m_v = e} (vars without a causal maximum count as never freed). Suite (§7.2 sizes): B_vars / W_vars =
1.1–2.4 (fib(10) 1,680 / 1,254, sort(15) 2,435 / 1,010). **W_vars bounds the semantic reducer only**: the fabric and
the RTL free a var when a LINK task or message is processed, any number of cycles after the interaction that created
it, so the live var count there can exceed every closed-prefix value. Admission (§7.4) therefore uses W_nodes and
B_vars. The task stack is still not bounded: atoms (ERA, NUM, REF) occupy no slot, so pending pairs are not bounded
by node and var slots; a bound needs an atom count per rule.

**CLI.** `python3 -m omega.eal --symbolic treesum [NMAX]` (or a `.olm` file with an `N`):

    treesum: Ω-L, symbolic bound in N (counted and certified on N = 0..13)
      recursion gen: numeric on parameter 1, ≤ 2^value unfolds
      recursion tsum: structural on parameter 1, linear in its size
      B_nodes(N) = 37·2^N - 23   [exact]
        growth 2^N (R allows <= 2^N); B_sym / counted: max 1.000, mean 1.000; sound on the range: True
      B_vars(N) = 32·2^N - 19   [exact]
        ...

### 7.4 Memory-bound admission control (step 25, `omega/admission.py`, fabric model)

§7.1 (3) names admission before the fabric fills as the missing piece for a completion guarantee; §7.2 / §7.3 give
the number to admit by. A job is a program with an owner (§12). An Ω-L job reserves **(W_nodes, B_vars)** (W_nodes
is sound on every implementation in which a node in flight holds no slot, so the live node count after any moment
is n0 + the deltas of a causally closed set of interactions; W_vars is not, §7.3); `bound="B"` reserves (B_nodes, B_vars).

**Rule.** With S node and S var slots per cell, a queued Ω-L job is started only if, for nodes and vars alike,

    Σ (reservations of the running Ω-L jobs) + its own  ≤  S − margin,   margin = 0 on one cell, D_max + max(LM_RSV, RSV) on a mesh.

Tenants share no slots, so the live graph of all running Ω-L jobs never exceeds the sum of their reservations, no
cell can hold more than that, and every cell keeps at least D_max + the reserve free: every expansion fits where it
is (the reserve never forces a hand-off) and every NODE / PULL finds a slot (rule (d) of §5 is never needed). This is
§7.2's argument applied to a sum of jobs, so the fabric never reaches the memory stall of §7.1 (3), and no job can
take another's memory. **Liveness:** jobs start in arrival order (FIFO, no overtaking); Ω-L jobs terminate, so a
queued job waits only for running jobs to finish. A job whose reservation exceeds the empty fabric's budget is
rejected at submission. One job per owner runs at a time (completion is detected per owner).

**Completion and release.** A job is done when its root var holds a value and no task, retry slot, var-hop link or
message anywhere carries a capability of its owner; the scheduler reads the result back, frees the owner's remaining
slots (the result went to the host) and releases the reservation. A queued job is loaded like the static image
(§6): its root var in its home cell, its `@main` nodes and vars from free slots starting there, its links on the
home cell's task stack.

**Untyped jobs** (not in Ω-L) keep the step-24 behaviour: admitted at once, unreserved; the guarantee covers only the
moments when no untyped job runs. **Off by default**: `fabric.Fabric` is unchanged, and `Scheduler(admit=False)` loads
every job at cycle 0, which is the step-24 multi-tenant behaviour. The RTL has no admission (it would need a host
loader that writes a job into a running mesh and a per-owner idle signal; not added in step 25), so RTL defaults are
cycle-identical to step 24.

**Cost.** The rule gives every cell the whole of every reservation (it knows nothing about placement), and B_vars is
2.3–35× an RTL 1×1 run's var peak (§7.2), so on small cells it admits about one job at a time: the 180-job flood below takes 176,707
cycles admitted; a 120-job flood that the unadmitted fabric still survives takes 49,770 cycles without admission and
119,814 with it. Tests (`tests/test_s25.py`): 180 jobs of 15 owners on 2×2 × 280 slots and 300 on 3×3 × 280 stop
without admission (no progress, no tenant finishes) and finish with it (every answer right, every cycle audited:
live ≤ reserved, every cell keeps the margin); a never-admissible job (treesum(9), W_nodes 7,166) is rejected while
the others finish; a job that fits only alone waits for the others; an untyped qsort passes through.
