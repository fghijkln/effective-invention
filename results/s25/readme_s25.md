### Symbolic bound B(N), a causal var bound, and memory-bound admission (step 25)

Step 24 gave a per-N bound (one counting run per input size) and named admission before the fabric fills as what a
completion guarantee needs (SPEC §7.1 (3)). Step 25 does both: **B(N) in closed form** for Ω-L programs
(`omega/symbolic.py`, SPEC §7.3), a **causal var bound W_vars** (`omega/causal.py`), and **admission control** for
multi-tenant fabrics in the fabric model (`omega/admission.py`, SPEC §7.4). No RTL, testbench or `fabric.Fabric`
change, so every default is cycle-identical to step 24 (identity 128 / 128).

**B(N).** R allows only structural recursion and recursion on `n - k`, and every rule has a fixed node delta and var
count, so when the work for N is fixed by N alone B(N) is C-finite (a linear recurrence with constant coefficients,
characteristic factors from the recursion offsets: x² − x − 1 for fib, x − 2 for a doubling recursion, (x − 1)^k for
straight-line work). The tool counts B(N) for N = 0, 1, …, finds the shortest recurrence by exact Berlekamp–Massey on
2L + 2 terms, solves it (rational roots → N^j·r^N terms, the rest via its fundamental sequence: Fibonacci for fib),
and certifies it: equal to the count at every N of the range (terms after the fitted ones held out), dominant root
within what R allows. `python3 -m omega.eal --symbolic treesum` prints `B_nodes(N) = 37·2^N - 23`.

| program | B_nodes(N) | B_vars(N) | certified (= the count) on N | tightness |
|---|---|---|---|---|
| fib | 24·F(N+1) − 14 | 19·F(N+1) − 11 | 0..21 (CLI), 0..22 (tests, 21–22 held out) | exact |
| sum, fact | 11·N + 7 | 8·N + 6 | 0..60 | exact |
| list | 54·N + 27 | 56·N + 23 | 0..60 | exact |
| higher | 43·N + 42 | 44·N + 43 | 0..60 | exact |
| treesum | 37·2^N − 23 | 32·2^N − 19 | 0..13 | exact |
| treesum_direct | 12·2^N − 8 | 9·2^N − 5 | 0..16 | exact |
| sort, any input of length N | ≤ 29/2·N² + 139/2·N + 24 | ≤ 27/2·N² + 121/2·N + 20 | 1..45 (≥ the count) | 2.0–2.1× its own input's B |

All suite formulas are exact from N = 0 (no piecewise table needed). **sort** depends on its data (the comparisons of
insertion sort), so its counted B(N) is not C-finite and the tool falls back to an upper envelope in the R class
(degree 2; on 0..45 at most 3.1× the count, no claim beyond the range). A data-independent bound comes from the
program (`results/s25/sort_decomp.py`): B_nodes = 24 + 84·N + 29·I − 21·nil exactly on N = 1..45 (I: insert steps
that go on, nil: inserts ending at Nil; vars 20 + 74·N + 27·I − 18·nil), and I ≤ N(N − 1)/2 gives the row above. The
same program with a descending input of the same template shape (`results/s25/sort_desc.olm`) is exactly
29/2·N² + 97/2·N + 24 / 27/2·N² + 85/2·N + 20, the ascending one 84·N + 3 / 74·N + 2 (N ≥ 1).
**Fuzz:** 40 random Ω-L programs (`tests/test_eal.py`'s generator, one size argument of `gen` / `tgen` / `nrec` /
`nlin` replaced by N): 38 exact closed forms (equal to the count on the range and on the next N, never fitted), 2
envelopes (data-dependent `filt` / insertion sort; ≥ the count on their range), 0 without a form.

**W_vars.** A var is freed by the second arrival at it, i.e. once every event of its arrival set F_v has happened; when
F_v has a causal maximum m_v this is "m_v done", so W_vars = v0 + max closure of (vars allocated − vars whose m_v this
is) over the causal DAG (others count as never freed). B_vars / W_vars on the step-24 sizes: fib(10) 1,680 / 1,254,
sum(100) 806 / 607, fact(12) 102 / 79, list(25) 1,423 / 918, sort(15) 2,435 / 1,010, higher(30) 1,363 / 908,
treesum(6) 2,029 / 1,333, treesum_direct(8) 2,299 / 2,044 (1.1–2.4×). At the test sizes (fib(8), sum(40), fact(12), list(12), sort(10), higher(12), treesum(5),
treesum_direct(6)) every lifo, fifo and 12 random semantic var peaks are below it (treesum_direct(6): fifo 446, W_vars 508). **It bounds the semantic reducer only**: the fabric and the RTL free a var when a LINK task or message
is processed, arbitrarily later, so they keep using B_vars.

**Admission.** A job (program + owner) in Ω-L reserves (W_nodes, B_vars) and starts only while, for nodes and vars,
the sum over running Ω-L jobs + its own ≤ slots per cell − margin (0 on one cell; largest template + the 16-slot
reserve on a mesh). The live graph of the running jobs then never exceeds the sum, so no cell holds more and every
cell keeps the margin free: no expansion is ever homeless and no NODE waits for a slot, and no job can take another's
memory. Jobs start in arrival order (FIFO; Ω-L jobs terminate, so a queued job only waits for running ones); a job
that cannot fit even an empty fabric is rejected at submission; untyped jobs start at once, unreserved (step-24
behaviour). Completion: root var holds a value and no task / retry / var-hop link / message carries the owner's
capability; the scheduler reads the result, frees the owner's slots and releases the reservation.

| scenario (`tests/test_s25.py`) | without admission (step 24: every job loaded at cycle 0) | with admission |
|---|---|---|
| flood: 180 jobs (sum(30), fib(5), treesum_direct(4), treesum(3), higher(4), fact(20)) of 15 owners, 2×2 × 280 slots | **stall** after 49,141 cycles: live 889 / 1,120 of 1,120 slots, 0 jobs finished | W: 180 / 180 correct, 176,707 cycles, peak live 68 / 96; B: the 60 jobs whose B exceeds the 252-slot budget rejected, 120 / 120 correct, 100,202 cycles |
| flood: 300 such jobs, 3×3 × 280 | **stall** after 62,895 cycles (live 1,679 / 2,515), 0 finished | 300 / 300 correct, 281,480 cycles |
| treesum(9) (W_nodes 7,166) + 18 small jobs, 2×2 × 200 | — | treesum(9) rejected at submission, 18 / 18 correct |
| treesum(5) (reserves 446 / 1,005 of 1,072) + 18 small jobs, 2×2 × 1,100 | — | the 18 start only after treesum(5) is done; 19 / 19 correct |
| untyped qsort(8) + 12 small jobs, 2×2 × 280 | — | qsort starts at cycle 0 unreserved; 13 / 13 correct |
| 24 small jobs on one cell × 150 | — | 24 / 24 correct |

Every admitted run is audited every cycle (live nodes / vars ≤ the reservations, every mesh cell keeps the margin
free): no violation. **Cost:** the rule gives every cell every reservation (it knows nothing about placement) and
B_vars is far above real var peaks, so on these small cells about one job runs at a time; a 120-job flood that the
unadmitted fabric survives takes 49,770 cycles without admission and 119,814 with it (2.4×). Reserving the
depth-first peak instead (mutant 13) runs the 180-job flood in 73,008 cycles but breaks the audit (live 98 / 174 >
reserved 242 / 172 at cycle 1,879): the throughput is there, a sound bound for it is not.

**Tests** (`tests/test_s25.py --fuzz 40`): 2,749 / 2,749 (synthetic recurrence units, suite + sort variants on the
range and past it, 40 fuzz programs, W_vars against 14 semantic orders × 8 programs, 7 admission scenarios).
**Mutants** (`--mutants`, `OMEGA_EAL_MUT` 8–13): 6 / 6 caught (fit accepted without the held-out terms, envelope
without its feasibility check, W_vars freeing at the first event, admission ignoring running jobs, reservations
never released, reserving the depth-first peak).

**Limits.** The closed form is certified on its range; beyond it, it rests on the C-finite argument (exact forms) or
on nothing (envelopes). The derivation is "count, then solve", not a type-level sized analysis, so it needs the
program to run for small N. Data-dependent programs get a data-independent bound only by a program-level argument
(sort). W_vars holds for atomic links only. The task stack is still not bounded (atoms occupy no slot). Admission
is in the fabric model only (the RTL would need a run-time job loader and per-owner idle detection); the per-cell
rule is conservative enough to serialise small cells; untyped jobs void the guarantee while they run.
