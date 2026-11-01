### 7.6 Quicksort in Ω-L (step 27, `programs/qsort_l.olm`)

`programs/qsort.olm` stays outside Ω-L (rule A: `qs` uses the tail `t` twice, once per `filter`) and is unchanged.
`programs/qsort_l.olm` computes the same result with three rewrites:

* **one partition, a pair.** `part(p, xs)` walks the list once and returns `P(lo, hi)`; `qs` matches the pair once,
  so every list is used exactly once (affine). Elements `< p` go left, the rest (duplicates of the pivot included)
  right, as in `qsort.olm`.
* **structural `part` and `app`** (recursion on the list argument, rule R structural).
* **numeric fuel for `qs`.** `qs(n, xs)` recurses on `n − 1` (rule R numeric), started at `n = N`; since each
  recursive call gets a strictly shorter list than its parent, `len(xs) ≤ n` always holds, so the fuel never runs
  out before the list does (the `0` arm is never reached with a non-empty list on any input). The checker records
  `qs: numeric, ≤ 2^value unfolds`.

**Bounds.** B (§7.2) depends on the data (how many elements each partition moves, how much `app` copies). The
counted B is exact in closed form (§7.3) for two input families of the program's own template shape: descending
(the worst case) **B_nodes = 32·N² + 86·N + 17, B_vars = 59/2·N² + 141/2·N + 15** and ascending 43/2·N² + 193/2·N
+ 17 / 41/2·N² + 159/2·N + 15, exact on N = 0..40 with held-out N = 41, 42; the program's own pseudo-random input
gets an envelope only. A data decomposition (`results/s27/decomp.py`) is exact on every one of 133 literal and 130
program inputs:

    B_nodes = 35 + 118·N + 43·P + 21·A − 9·Z,   B_vars = 27 + 100·N + 41·P + 18·A − 6·Z

with P = elements moved by partitions (Σ over `qs` calls of the partitioned length), A = `app` steps, Z = `qs`
calls at fuel 0 (0 or 2). P ≤ N(N − 1)/2, A ≤ P, and Z = 2 only at the full chain, so with positive P and A
coefficients the maximum over every input of length N ≥ 1 is P = A = N(N − 1)/2, Z = 2: exactly the descending
closed form. **The worst-case envelope is attained and holds for every input**, not only the sampled ones. W (§7.3,
causal) is 3.6–6.9× below B_nodes and 2.0–2.5× below B_vars at N = 2..12, and above every semantic peak (5 orders).

**Cost.** qsort_l does fewer interactions than qsort (0.78× at N = 40: one pass per partition instead of two
filters) but is slower on a mesh (RTL 2×2: +36% cycles at N = 12, +32% at N = 30), because `part` returns its pair
only after the whole list was walked and `app` waits for the left half, so less work overlaps.
