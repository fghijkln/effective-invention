### Quicksort in Ω-L (step 27)

Step 24 left qsort as the one suite program outside Ω-L (it duplicates a list: `lo(h, t)` and `hi(h, t)` both use
`t`). Step 27 adds an Ω-L rewrite next to it, `programs/qsort_l.olm` (`qsort.olm` is unchanged): one structural
`part(p, xs)` returns both halves as a pair `P(lo, hi)` that `qs` matches once, `app` is structural, and `qs(n, xs)`
recurses on a numeric fuel `n` started at N (each call's list is shorter than its parent's, so `len(xs) ≤ n` and the
fuel never runs out first). Same answer as qsort and Python's `sorted` on 182 inputs (N = 0..40, several seeds,
ascending, descending, constant, duplicates), on the fabric model (1×1, 2×2, 4×4) and on the RTL. SPEC §7.6.

| | qsort_l | note |
|---|---|---|
| Ω-L | accepted (`qs` numeric fuel, `part` / `app` / `check` structural) | qsort still rejected (rule A) |
| B, worst case over every input of length N ≥ 1 | **B_nodes = 32·N² + 86·N + 17, B_vars = 59/2·N² + 141/2·N + 15** | the descending input's exact closed form (N = 0..40 + 2 held out), attained |
| why it is the worst case | B_nodes = 35 + 118·N + 43·P + 21·A − 9·Z, B_vars = 27 + 100·N + 41·P + 18·A − 6·Z, exact on 263 inputs | P = elements partitioned ≤ N(N−1)/2, A = app steps ≤ P, Z = fuel-0 calls ∈ {0, 2} |
| ascending input | 43/2·N² + 193/2·N + 17 / 41/2·N² + 159/2·N + 15 (exact) | the program's own random input: envelope |
| B / W (causal) at N = 2, 4, 8, 12 | nodes 317 / 88, 721 / 154, 1,813 / 280, 2,842 / 412; vars 274 / 137, 627 / 277, 1,604 / 644, 2,527 / 994 | W ≥ every semantic peak of 5 orders |
| RTL 1×1 with exactly B slots | N = 0, 1, 4, 8, 12 finish correctly; peaks (14, 14), (21, 28), (53, 77), (91, 134), (111, 170) | B / peak at N = 12: 26× nodes, 15× vars |
| interactions vs qsort | 0.97× (N = 5), 0.88× (10), 0.83× (20), **0.78× (40)** | one partition pass instead of two filters |
| RTL 2×2 cycles vs qsort | 4,979 vs 3,671 (N = 12, +36%), 14,238 vs 10,788 (N = 30, +32%) | the pair is ready only after the whole list was walked, so less overlaps |

So qsort can now be admitted (step 26) and certified at a size: e.g. qsort_l(12) needs 2,842 / 2,527 slots on one
cell. It is a slower program on a mesh, so the benchmarks keep `qsort.olm`. Tests (`tests/test_s27.py`): **253 / 253**
(Ω-L verdicts, semantic / fabric / RTL correctness, B ≥ all semantic and fabric peaks, W between peaks and B,
closed forms with held-out N, the decomposition exact on every input and its maximum equal to the descending form,
RTL 1×1 at exactly B, RTL 2×2 vs qsort).

### Memory-bound admission control in the RTL (step 26)

Step 25 admitted jobs only in the fabric model. Step 26 builds the same rule into the RTL: a controller beside the
mesh (`rtl/omega_adm.sv`) with a 512-entry job table, a 16-slot root-var pool in cell (0,0), running reservation
sums, an owner-busy vector and a host port into cell (0,0). SPEC §7.5. **Run-time knob `+adm` (testbench plusarg; `omega/adm_rtl.py` sets it),
default 0 = step 25 cycle for cycle** (identity 128 / 128).

* **Decision** (when the head of the FIFO reaches it): typed job with a reservation above the budget → reject;
  owner idle, a root slot free and (typed) Σ running reservations + its own ≤ slots − margin for nodes and vars →
  start; untyped → start unreserved; otherwise wait. Same budget, same margin, same FIFO as `omega/admission.py`.
* **Start:** reset the root var slot through var write port 1 when the engine leaves it free, then hand cell (0,0)
  the task {REF @main, VAR root}, taken as a SPAWN (expand there or hand on): `@main` is placed by the cell's own
  allocator and spawn / pressure policy. A var ~ var link never writes into a pool root (the other var takes it),
  so the controller's shadow copy of the root is the result.
* **Completion:** at mesh quiescence every running job is done; the controller sweeps the roots, frees the owner,
  and for an atom result frees the root and releases the reservation (a data result stays in the fabric and keeps
  both, since the RTL has no host unload).
* **Audit** (simulation): every cycle live nodes / vars ≤ reserved (while no untyped job runs), reserved ≤ budget,
  every mesh cell keeps the margin free.

Cross-check against the fabric-model scheduler on the same job lists (`tests/test_s26.py`; rejected set, start order
and total interactions must match, every admitted job correct, zero audit violations, no owner overlap):

| scenario | jobs | RTL (+adm=1) | fabric model (step 25) | without admission (RTL, +adm=0) |
|---|---|---|---|---|
| flood 2×2 × 280, W | 180 (sum, fib, treesum_direct, treesum, higher, fact; 15 owners) | 180 / 180 correct, 97,345 cycles (seed 2: 97,378), peak live 61 / 84, max reserved 129 / 246 of 252 | 180 / 180, 176,707 cycles; 46,620 interactions both | **stops** after 26,564 cycles (1,733 interactions) |
| flood 2×2 × 280, B | 180 | 60 rejected (same 60), 120 / 120 correct, 56,482 cycles | 60 rejected, 120 / 120, 100,202 | — |
| flood 3×3 × 280, W | 300 | 300 / 300, 158,710 cycles | 300 / 300, 281,480; 77,700 interactions both | **stops** after 24,425 cycles |
| reject: treesum(9) + 18 small, 2×2 × 200 | 19 | treesum(9) rejected, 18 / 18 | same | — |
| queue: treesum(5) first, 2×2 × 1,100 | 19 | the 18 start only after treesum(5) ends; 19 / 19 | same order | — |
| untyped qsort(8) + 12, 2×2 × 280 | 13 | qsort starts first, unreserved; 13 / 13 | same | — |
| one cell × 150 | 24 | 24 / 24 | same | — |
| 18 jobs of 3 owners, 2×2 × 600 | 18 | 18 / 18, no overlap within an owner | same order | — |

Tests 76 / 76; **mutants 60–64: 5 / 5 caught** (`OMEGA_S26_MUT`: admission ignores running reservations → audit
violations; no reject check → wrong reject set; two jobs of one owner at once → overlap; root not reset → controller
blocked; reservations never released → blocked). The RTL needs fewer cycles than the model's estimate (the model is
cycle-approximate); decisions and interaction counts are identical. **Limits:** completion only at global quiescence (a job finished early keeps
its reservation until the mesh is idle); data results stay in the fabric and keep their reservation; one start per
cycle at most, through cell (0,0) only; the job table is written before the run (no run-time submission port).

