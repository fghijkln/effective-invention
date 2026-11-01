### 7.2 Ω-L: a compile-time peak-memory bound (step 24, `omega/eal.py`)

§7.1 (3) leaves completeness open because the peak live graph depends on the schedule, which the fabric picks
locally. Step 24 closes it *statically* for a typed subset: for a program the compiler accepts, it computes a
number B such that **no schedule** of that program ever has more than B live nodes or vars, so a cell (or
every cell of a mesh) given B slots can never hit the memory stall of §7.1 (status 3 / "no progress").

**Bound.** For a net that normalises, every maximal reduction fires the same multiset of interactions: two distinct
active pairs share no node, so firing one leaves the other in place with the same rule (diamond property; the
interaction count of §9 is the one-number shadow of this). Each rule instance has a fixed node delta Δ (expansion of
definition d: +|d.nodes|; commutation +2; `SWI` on a non-zero number +1; `OPR` swap 0; everything else < 0) and a
fixed number of var allocations (expansion |d.vars|, commutation 4). Hence

    B_nodes = n0 + Σ_i max(0, Δ_i)        B_vars = v0 + Σ_i (vars allocated by i)

are properties of the program, not of a schedule (n0 / v0: the loaded `@main` template and the root var). After
any schedule prefix P the live node count is n0 + Σ_{i∈P} Δ_i ≤ B_nodes and the live var count is at most the vars
allocated so far ≤ B_vars. This holds for every implementation that frees a rule's consumed nodes in that rule
and allocates exactly the rule's slots: the semantic reducer, the fabric model and the RTL (a `NODE` / `PULL` in
flight holds no slot; var slots are freed by the second arrival, which only lowers the live count).
Vars use allocations, not deltas, because which interaction frees a var depends on which side arrives second.

**No memory stall.** One cell with B_nodes node slots and B_vars var slots never lacks room: an expansion needs
|d.nodes| free slots, and live-before + |d.nodes| = live-after ≤ B. On a mesh every cell is given
`slots_mesh` = max(B_nodes, B_vars) + D_max + max(`lm_rsv`, `rsv`) slots (D_max = the largest template, 12 in the
suite): no cell can hold more than the whole live graph, so every cell always keeps at least D_max + 16 free, every
expansion fits where it is (the reserve never forces a hand-off) and every `NODE` / `PULL` finds a slot (rule (d)
is never needed). Not covered: the task stack (`err` 1, status 2: sum(1000) needs a 1,005-entry stack on one
cell), cycle limits, and programs outside Ω-L.

**Ω-L (the subset).** The counting needs a terminating program; Ω-L is a light-affine, stratified (box depth 1)
subset of Ω-lang whose programs all terminate. `eal.check` adds four rules to the frontend's checks:

* **T (types).** Hindley–Milner as in §10, but every constructor field has *one* type in the whole program
  (step 6 gave it a fresh type at every use) and no field holds a function. Otherwise data can hide self
  application: `data Box = B(f)`, `def w(x) = unbox(x)(x)`, `def main = w(B(w))` is accepted by step 6 and loops.
* **A (affinity).** A binder whose type is not `Num` is used at most once in every net template the compiler
  emits, counted exactly as `Compiler.compile_def` counts (after arm lifting: an inline value arm shares its
  binders with its siblings, a lifted arm gets them as one argument each). Numbers are free to duplicate
  (`DUP ~ NUM` copies an atom); a data value never is, so a match takes every data cell apart at most once.
  A binder whose type is still a type variable counts as non-number (conservative).
* **! (duplicable closures).** A binder of function type may be used several times only if it is a parameter of
  its definition (a !-parameter: `map`'s and `foldr`'s `f`, `twice`'s `f`), and every call site passes there an
  *inert closure*: a λ literal over its own variables, numbers, operators and applications, whose free variables
  are numbers or the caller's !-parameters, or a definition name, or the caller's own !-parameter. Nothing that
  is duplicated contains a definition reference, so a copy costs at most the literal's node count and never
  copies pending work (box depth 1). Partial applications of a definition with a !-parameter are rejected.
* **R (recursion).** In every strongly connected component of the call graph each recursive call decreases a
  measure parameter of its callee (one per definition, found by search): a *structural* sub-term (a field of a
  `match` on that data parameter, at any depth, through `let` aliases) or a *guarded numeric* predecessor (`p` of
  `switch n`, `n - k` / `p - k` where an enclosing `switch n`, `if n < c`, `if n <= c`, `if n == 0` proves that
  the u32 subtraction cannot wrap). A recursive definition used as a value (recursion through a closure) is
  rejected; so are lexicographic measures (Ackermann).

Termination (an argument, not a machine-checked proof): a recursive call only unfolds when its lifted arm is
selected by a `SWI` / `match` on a value, and the measure strictly decreases on a well-founded order (u32 without
wrap, or sub-terms of a finite first-order data value); the rest is an HM-typed λ-calculus, which is strongly
normalising, and rule T keeps functions out of data; rules A and ! bound every copy by a static size.

**Computing B.** EAL / LAL give *generic* bounds (elementary / polynomial in the input size), and Ω-L's
stratification gives the same kind: per component, a numeric recursion with fan-out c unfolds ≤ c^n times
(`eal.growth`), a structural one once per data cell, composed along the component DAG into a tower whose height
is the DAG depth. These are sound but useless as slot counts (fib(20): ≤ 2^21 calls × 15 template nodes
≈ 3.1·10^7 against B_nodes = 262,690). Since an Ω-L program terminates, the compiler instead runs a
**counting reduction** of the closed program once (`eal.bound`: the semantic reducer's rule bookkeeping, no
placement or messages; treesum_direct(14), 245,750 interactions: 1.7 s) and reads B off exactly. This is
compile-time partial evaluation of a closed program, not a symbolic bound in N; the CLI reports both:

    python3 -m omega.eal programs/treesum.olm --N 9      # or: python3 -m omega.eal treesum 9
    programs/treesum.olm: in Ω-L
      recursion gen: numeric on parameter 1, ≤ 2^value unfolds
      recursion tsum: structural on parameter 1, linear in its size
      bound: nodes 18921, vars 16365 (n0 2, v0 3, 18410 interactions)
      depth-first peak (semantic): nodes 67, vars 97
      slots: one cell 18921, every mesh cell 18943 (largest template 6)

**How tight.** B is a bound over *all* schedules, so it cannot be below the worst schedule. A tighter all-schedule
bound for nodes is the max-weight closure W of the causal event DAG (`results/s24/worst.py`: an interaction
depends on the events that created its two nodes and on those whose links joined the wire that made the pair
active; live nodes after a prefix = n0 + the weight of a causally closed set; W = n0 + max closure by min cut).
W is the same from six different recorded orders. B / W = 1.7–2.9 on the suite (9.2 for sort), and breadth-first
order reaches up to 75% of W (treesum(9): 5,375 of 7,166), so B is within 2–4× of schedules that really occur.
The depth-first peaks the fabric and the RTL reach are far lower (README step 24: at the sizes the RTL check runs, B is 5–102× the RTL 1×1 peak in nodes and 2.3–35× in vars, and the ratio grows with N for the exponential programs), so
B answers "is this program safe on this fabric under any schedule", not "how small can a cell be".
There is no var analogue of W yet (the freeing event is order dependent), and the cells are sized by
max(B_nodes, B_vars).

**Which programs.** In Ω-L: fib, sum, fact, list, treesum, treesum_direct, sort, higher (8 of the 9 suite
programs) and 10 of the 15 frontend unit programs. Rejected: qsort (A: `t` goes to both `lo(h, t)` and `hi(h, t)`;
R would reject `qs(lo(h, t))` too), Church `two(two)` (box depth 2), Ackermann (lexicographic), a default binder that
aliases the scrutinee (A: `other` copies the matched value), a pair with a number in one place and a constructor in
another (T), a list of functions (T). Checker / bound mutants (`OMEGA_EAL_MUT` 1–7, `tests/test_eal.py --mutants`)
are all caught.
