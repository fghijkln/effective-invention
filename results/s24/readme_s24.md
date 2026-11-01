### Ω-L: a typed subset with a compile-time peak-memory bound (step 24)

SPEC §7.1 (step 20) showed that no local mechanism can guarantee completion: the peak live graph depends on the
schedule, and the fabric picks the schedule. Step 24 bounds that peak at compile time for a typed subset of Ω-lang,
**Ω-L** (`omega/eal.py`, SPEC §7.2), so that a fabric with enough slots per cell provably never reaches the memory
stall (status 3). No RTL or model change: the step adds a checker, a bound, a CLI and tests.

* **Subset.** Light affine and stratified (box depth 1), in the spirit of EAL / LAL: (T) Hindley–Milner with *one*
  first-order type per constructor field; (A) a non-number binder is used at most once in every net template the
  compiler emits (counted after arm lifting, exactly as the compiler counts DUPs), so data is never duplicated;
  (!) a function may be duplicated only as a parameter that every call site feeds an inert closure (a λ literal
  over its own variables, numbers and operators, a definition name, or the caller's own !-parameter); (R) every
  recursive call decreases a structural sub-term or a guarded numeric predecessor of its callee. Together these
  make every Ω-L program terminate.
* **Bound.** Strong confluence makes the multiset of interactions the same for every schedule, and each rule has a
  fixed node delta and var allocation count, so **B_nodes = n0 + Σ max(0, Δnodes)** and **B_vars = v0 + Σ vars
  allocated** bound the live nodes and vars of *every* schedule on the semantic reducer, the fabric model and the
  RTL. Because the program terminates, the compiler reads B off one counting reduction of the closed program
  (`eal.bound`; 1.7 s for treesum_direct(14)'s 245,750 interactions). One cell needs max(B_nodes, B_vars) slots; a
  mesh needs that + the largest template + the 16-slot low-memory reserve in every cell (`slots_mesh`). The
  generic stratification bound (fan-out^depth unfolds per recursion, printed as a growth class) is sound but far
  looser (fib(20): ≈ 3.1·10^7 nodes against B_nodes = 262,690), so it is not used for slot counts.
* **CLI.** `python3 -m omega.eal programs/treesum.olm --N 9` (or `python3 -m omega.eal treesum 9`) prints the
  verdict (or the rule a program breaks), the recursion classes, the !-parameters, B and the slot counts.

**Which programs are in Ω-L** (`tests/test_eal.py`, census): 8 of the 9 suite programs (fib, sum, fact, list,
treesum, treesum_direct, sort, higher; all their N, since N only changes `main`'s literal) and 10 of the 15
frontend unit programs. Rejected: **qsort** (A: the list tail `t` goes to both `lo(h, t)` and `hi(h, t)`; `qs(lo(h, t))`
is not structural either), Church `two(two)` (a closure that duplicates is duplicated: box depth 2, which full EAL
would accept), Ackermann (lexicographic measure), a default binder that aliases the matched value (A), a pair holding
a number in one place and a constructor in another (T), a list of functions (T). Of the 315 program-suite cases,
everything except the qsort cases (fork / producer / deque hints of qsort, its fabric and RTL runs and its fuzz
draws) is a program in Ω-L.

**Tightness** (`results/s24/table.md` from `tests/test_eal.py --json results/s24/eal.json` and
`results/s24/table.py`; peaks are node / var slots; fabric seeds 0 / 9, RTL seed 2 at the default
configuration; the semantic breadth-first order is FIFO over the redex list):

TABLE

* **B holds everywhere:** every semantic order (5 per case), fabric run (1×1, 2×2, 4×4; whole mesh and per cell)
  and RTL run stays below B, B is identical from all 5 orders, and an independent recount gives the same B.
* **With exactly B slots the RTL finishes.** A 4,096-slot 1×1 cell with ballast leaving exactly B_nodes − n0 free
  node slots and B_vars − v0 free var slots (so the program has B of each) finishes with the right answer for all 8
  programs above and for 30 typed fuzz programs; a 2×2 mesh whose every cell keeps `slots_mesh` free finishes for
  fib(8), list(20), treesum(5), sort(10), higher(30).
* **How loose.** B is an all-schedule bound, so it cannot go below the worst schedule. The causal bound W (max-weight
  closure of the interaction DAG, `results/s24/worst.py`; the same W from six different recorded orders) is
  B / 1.7–2.9 on the suite (sort B / 9.2), and the breadth-first order reaches up to 75% of W (treesum(9): 5,375 of
  7,166 nodes), so B is within 2–4× of schedules that really happen. But the fabric and the RTL reduce close to depth
  first: B is 5–102× their 1×1 peak in nodes and 2.3–35× in vars at these sizes, and the ratio grows with N for the
  exponential programs (treesum(9): B_nodes 18,921 against an RTL 1×1 peak of 281). B is the answer to "is this
  program safe on this fabric under any schedule", not a cell size to build.
* **Typed fuzz** (`--fuzz 200 --rtl-fuzz 30`): 200 random Ω-L programs from producers (lists from a seeded
  recurrence, trees), transformers (map with a random inert closure, filter, append, insertion sort, reverse,
  tree map / mirror / flatten), consumers (weighted checksum, fold with a random closure, tree sum) and numeric
  recursions (fan-out 1 and 2 with random guards), with random sizes: all accepted, B ≥ every peak (5 semantic
  orders, one fabric run on a random mesh, 30 on RTL 1×1 with exactly B slots), B / semantic peak median 3.6 for
  nodes (1.0–10.9) and 2.8 for vars (1.0–8.2). Each fuzz program is also broken in one way (a duplicated list, a
  non-decreasing call, an increasing argument, a non-inert closure to a !-parameter, a function in a data field) and
  must be rejected for that rule: 200 / 200.
* **Mutants of the checker and the bound** (`OMEGA_EAL_MUT`, `tests/test_eal.py --mutants`): 7 / 7 caught (affinity
  off, any closure duplicable, termination check off, commutation nodes / vars not counted, constructor fields typed
  per use, numeric guards ignored).

**Limits.** B is computed by a counting run, not symbolically in N (one run per N; a program outside Ω-L may not
terminate, so the compiler never runs one). The var bound counts allocations; there is no var analogue of W yet.
The task stack is not bounded (sum(1000) needs 1,005 entries on one cell). Ω-L makes no claim about the
interaction-combinator oracle problem (DUP labels are still one per binder; box depth 1 keeps the suite clear of
it). B covers memory slots only: a fabric with B slots can still stop on a cycle limit or a full task stack.
