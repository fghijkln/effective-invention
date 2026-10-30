# TACHYON-Ω — a Spatial Interaction-Net Fabric

> **Scope statement / 项目范围声明**
>
> TACHYON-Ω is an architecture and RTL project. Tape-out, physical design, place-and-route, timing closure, power, process nodes and silicon cost are **out of scope — permanently**. The area and Fmax figures in this repo are rough pre-layout estimates kept for internal reference only; they are not claims and not an invitation to debate. Reviews, issues or comments that judge this project on fabrication or physical-design grounds will be closed without discussion.
>
> 本项目只关注体系结构与 RTL。流片、物理设计、布局布线、时序收敛、功耗、工艺节点与硅成本**永久不在范围内**。仓库中的面积与 Fmax 数字仅为布局前粗略估算，仅供内部参考，不构成任何主张，也不接受讨论。任何以流片或物理设计为由对本项目做出的评价、issue 或评论，一律不予回应、直接关闭。

A processor prototype with **no CPU, no separate memory, no program counter, no shared address space
and no instruction stream**. A program is a graph (an interaction net). The machine is a W×H mesh of
*active memory cells*. Each cell stores part of the graph and rewrites, right where it is stored, the
active pairs it holds. Cells cooperate only by passing messages to their four neighbours. The result is
the normal-form graph left in the cells' RAMs.

Status: **MVP+**. It has a semantic golden model, a cycle-level fabric model, a frontend for a small
functional language, SystemVerilog RTL (Verilator) for 1×1 to 8×8 meshes, owner-capability isolation
for several mutually distrusting programs on one fabric, differential fuzzing under randomised
schedules, mutation testing and benchmarks. Repository: https://github.com/fghijkln/effective-invention
(CI: `.github/workflows/ci.yml` runs `tests/ci_quick.sh` on every push).

* Specification: [SPEC.md](SPEC.md) (model, encodings, rule table, message protocol, cell
  microarchitecture, back-pressure, termination).
* Computation model: Lafont interaction combinators + numbers/operators/switch/references, as in HVM2
  (Taelin, paper.higherorderco.com). Labelled duplicators and the minimal local rule set follow the
  spirit of Δ-Nets (arXiv 2505.20314). Optimal reduction is *not* implemented.

## Why this is not a von Neumann machine

| von Neumann property | TACHYON-Ω |
|---|---|
| CPU and memory are separate; data travels to the ALU over a bus | Every memory cell has its own rewrite engine. A rewrite reads and writes only the cell's own node/var RAM. Data moves only when two halves of an active pair live in different cells, and then the *node* migrates (NODE message), not a load/store |
| A program counter selects the next instruction | There is no PC and no instruction fetch. A cell acts only because it holds an active pair or received a message. Order is irrelevant (strong confluence), so there is nothing to sequence |
| Program = instruction stream in memory | Program = graph. The definition ROM holds **graph templates** (expanded lazily by `REF`), never control flow |
| One shared, flat address space | Every pointer names an owner cell `(x, y, slot)`. Only the owner touches a slot. Other cells must send it a message, and there are no global loads/stores |
| Synchronisation through shared memory / locks | None needed. A var's two ends are joined by its owner cell, one exchange at a time: HVM2's lock-free `link`, with the atomic swap replaced by single-owner serialisation |
| Global control | The only global wires are clock, reset, the verification knobs and the quiescence AND-tree (termination). Work distribution uses neighbour-local `hungry` wires |

## Quick start

```bash
bash ../cpu128/tb/setup_toolchain.sh && source ~/env.sh      # rootless Verilator (same as TACHYON-128)
export PYTHONPATH=.
python3 -c "from omega import progs, lang, semantic; print(lang.compile_source(progs.source('fib', 10))); print(semantic.result(progs.book('fib', 10))['readback'])"
python3 tests/test_units.py --rtl        # directed rule tests on semantic + fabric + RTL 1x1/2x2/4x4
python3 tests/test_programs.py --fuzz 150
python3 tests/fuzz_rtl.py 0 600          # random nets, random meshes, random schedules
python3 tests/fuzz_rtl.py 0 200 --big
python3 tests/test_security.py --fuzz 300   # owner-capability isolation (multi-tenant)
python3 tests/mutants.py                 # 22 RTL mutants
python3 bench/bench.py --8x8             # results/bench.md
bash tests/run_all.sh                    # everything except the benchmarks
```

Example Ω-lang program (`programs/treesum.olm`):
```
data Tree = Leaf(v) | Node(l, r)
def gen(d) = switch d { 0 => Leaf(1); p => Node(gen(p), gen(p)) }
def tsum(t) = match t { Leaf(v) => v; Node(l, r) => tsum(l) + tsum(r) }
def main = tsum(gen(N))
```

## Layout

| path | contents |
|---|---|
| `omega/ports.py` | 64-bit port / 128-bit node encoding, ALU semantics |
| `omega/ir.py` | text IR (HVM2-style `@main = ...`) parser/printer, flat definition templates |
| `omega/semantic.py` | **golden model (a)**: any-order reducer (random / LIFO / FIFO), readback |
| `omega/fabric.py` | **golden model (b)**: cycle-level fabric (cells, routers, LINK/NODE/SPAWN), loader `Image` (+ hex image for the RTL), dump readback |
| `omega/lang.py` | Ω-lang frontend (λ, numbers, `let`, `if`, `switch`, `match`, Scott `data`, recursion; arm lifting) |
| `omega/randnet.py` | random interaction-net generator |
| `omega/rtl.py` | Verilator build/run harness |
| `rtl/omega_defs.svh` `omega_router.sv` `omega_cell.sv` `omega_rom.sv` `omega_mesh.sv` | RTL: encodings; 5-port XY router; cell (RAMs, owner tags, free stacks, task stack, directory, rewrite FSM); cluster definition ROM with round-robin arbiter; W×H mesh |
| `tb/tb_mesh.cpp` | testbench: reset, run to quiescence, dump |
| `programs/*.olm` | fib, sum, fact, list map/sum, tree build+sum, direct tree sum, insertion sort, quicksort, higher-order |
| `tests/test_security.py` | owner-capability isolation: multi-tenant demos, attacks, fault injection, multi-tenant fuzz |
| `tests/` `bench/` `results/` | test suites, benchmarks, logs |

## Results

### Verification (full regression on step 20 = step 19 with slot reserve 1 (`+rsv=1`), defaults `+rto=8 +rgrad=3 +rsv=1`; step 19 = step 18 + the room-distance gradient: v4 engine + retry slot + spawn threshold / fork hints + local-first link orientation + producer hint / message-budget governor + fork deque with the step-15 deque hint; default 2×2 cells per ROM, one port)

| suite | result | what it checks |
|---|---|---|
| directed rule/unit tests (`tests/test_units.py --rtl`) | **42 / 42** | every rule of the rule table (25 hand-written nets with expected normal form *and* interaction count) + 15 frontend programs (closures, Church numerals, Ackermann, mutual recursion, `match`; nested / literal / default patterns, `let`, a polymorphic helper) + 15 programs the frontend must reject (one check) + IR round trip. Each net runs on the semantic model (random, LIFO, FIFO order), the fabric model and the RTL on 1×1, 2×2, 4×4 with jitter/stalls and scattered loading |
| program tests (`tests/test_programs.py --fuzz 150`) | **315 / 315** | 9 programs × N = 0..5 (semantic), the step-11 fork hint, the step-13 producer hint and the step-15 fork-deque hint (bit 59) of all 9 programs (exactly the divide-and-conquer recursions are fork targets, exactly the data-emitting linear recursions are producers, exactly the numeric non-stream-fed forks go on the deque), each program on the fabric model and on RTL 1×1/2×2/4×4 × 2 schedules + a third on 2×2/4×4 (schedule 0: default spawn policy with the governor; schedule 1: the step-10 policy; schedule 2: fixed producer threshold, governor off, so every decision path stays covered), a performance bound (tree sum 4×4 ≥ 3× 1×1), a message bound (qsort(20) and list(40) on 4×4 ≤ 0.6 messages per interaction and no slower than 1×1), and 150 random (program, N, mesh incl. 3×2 and 1×4, seed, jitter, stall, priority, scatter, spawn thresholds, producer threshold, governor budget, link orientation, fork-deque mode) cases; the three fixed schedules run with the step-14 default |
| step-14 cross-check (`tests/test_s14.py`) | **90 / 90** | fib, treesum, treesum_direct, qsort, list, higher on 2×2 / 4×4 / 3×2 with fork-deque mode 0 / 1 / 2 and the governor relax on (nb5l1) / off: fabric model and RTL both equal the semantic reducer (readback, interactions, RTL node count), and the oldest-fork give happens in *both* models exactly where it should (fork programs in mode 1 and 2, qsort only in mode 1, never in mode 0); the fabric-only knob suite `tests/test_fabric_var.py` passes 1,782 / 1,782 over all 22 knob configurations (step 15 run; step 14 ran 4 of them, 324 / 324) |
| RTL differential fuzz, small nets (`tests/fuzz_rtl.py 0 600`) | **600 / 600** | random books (all node kinds, 3 DUP labels, all 16 operators with both flip bits, SWI, REF DAGs) on 1×1, 2×2, 4×4, 3×2, 1×4 with random arbitration seed, link jitter (0–63%), engine stalls, message/task priority, random scatter of `@main` over the cells, random spawn thresholds / fork-hint use (step 11), link orientation (step 12), producer threshold and governor budget 0–200 (step 13), fork-deque mode 0 / 1 / 2 (step 14). Readback, interaction count and live node count must equal the semantic model's (165 diverging nets rejected) |
| RTL differential fuzz, big nets (`--big`) | **200 / 200** | 3–8 definitions, 20–60 nodes each, deeper trees, more references; only nets with ≥ 30 interactions are kept (avg 375, max 16,239 interactions; 4,088 candidates rejected as diverging or trivial) |
| owner-capability isolation (`tests/test_security.py --fuzz 300`) | **420 / 420** | 2- and 4-tenant program demos (fib ∥ qsort; treesum ∥ list ∥ sort ∥ higher-order) on 1×1/2×2/4×4/3×2, each tenant gets its known answer with zero traps; 10 attack programs (overwrite / capture the victim's result through a forged root-var pointer, out-of-bounds slot and cell, forged node pointers to the victim's result node, an attack hidden in a lazily expanded definition) and 3 cross-owner fault injections, each with the sender-side check on and off (`fi`); 300 random multi-tenant cases (2–4 random tenants, random owners, half with an attacker carrying random forged redexes); link orientation (step 12) varies with the seed. Semantic model, fabric model and RTL must agree on every honest tenant's result and node count, on the trap set and on the interaction count (SPEC §12) |
| memory pressure (`tests/test_mempress.py`) | **44 / 44** | cell (0,0) pre-filled with foreign ballast so only 4–30 slots are free (30 cases), small-cell capacity cases (5), **global pressure (step 10, 5 cases): every cell except the far corner holds ballast (8 free node / 8 free var slots), so the room is up to 6 hops away** (fib(12) 3×3, treesum(6) 3×3, list(20) 3×2, qsort(15) 4×4, sort(10) 3×3) + **the near-overfull global treesum(9) 3×3 (step 19)**, security fuzz case 265 — semantic model, fabric model and RTL must agree; **2 overfull cases** (the whole 2×2 fabric too small) must end in status 3 without a wrong answer |
| mutation testing (`tests/mutants.py`) | **52 / 52 caught** | 15 functional mutants of the rule logic / protocol / quiescence + 1 performance mutant (no work distribution, caught by the speed-up bound) + 6 security mutants (each owner-capability check disabled, owner stamping missing, trap not blocking). Two mutants (eraser reaches only aux1; REF~DUP expands instead of copying) produce the *right* answer and are caught only by the node count / interaction count. That is why all three observables are compared. + 5 v3 engine mutants (read-ahead write bypass, write-queue drain, var owner-tag queue, allocation pop count, ROM read-ahead) + 2 memory-pressure mutants (caught by `tests/test_mempress.py`) + 3 cluster-ROM mutants (grant beyond the port count, EXPAND not waiting for its template word, stale buffered word) + 7 v4 mutants (second node write port not bypassed into the read-ahead, second EXPAND entry's var tag to the wrong slot, EXPAND skipping an entry, VHU without the same-slot stall, VHU hand-back never taken, VHU disabled = performance mutant caught by a fib(12) cycle bound, VHU read-ahead without bypass of write port 1) + 3 retry-slot mutants (39 parked retry never taken, 40 quiescence ignores the slot, 41 no escalation). Mutant 27 (roomy offload disabled) now survives on its own, because escalation also rescues every pressure case (roomy offload became a fast path); it is run together with 41 and caught. Mutant 28 (a full cell still asks for work) is tolerated by the step-19 full-cell pass-on on the quick pressure set, so since step 19 it runs on the full set and is caught by the global treesum(9) 3×3 case. + 3 step-11/12 performance mutants, each caught by its own bound: 42 spawn threshold ignored (qsort(20) 4×4 > 0.6 messages per interaction), 43 fork hint ignored (fib(12) 4×4 > 1.3× slower), 44 local-first link orientation disabled (treesum(7) 4×4 > 1.3× more LINKs) + 2 step-13 performance mutants: 45 producer hint ignored (qsort(30) 4×4 > 1.15× slower: 11,383 vs 9,118 cycles), 46 governor never tightens (qsort(30) 4×4 > 1.15× more messages per interaction: 0.529 vs 0.398) + 2 step-14 mutants: 47 oldest-fork give disabled (performance only: fib(16) 4×4 seed 1 > 1.05× slower, 8,254 vs 7,530 cycles; a treesum(7) bound let it survive at 1.04×, because the step-11 path still gives a fork task popped from an empty stack), 48 a fork task finding the deque full is dropped (caught by the program suite: fib(8) 2×2 loses work) + 2 step-19 mutants, each caught by the livelock / deadlock seeds that motivated the change at the new default: 49 room-distance gradient ignored (global treesum(9) 3×3 seeds 3 / 10 / 11 stop without progress), 50 full-cell pass-on off (global treesum(7) 8×8 seeds 16 / 18 stop at ~4,560 of 4,586 interactions; since step 20 the detector runs them at `+rsv=4`, because reserve 1 lets both finish without the pass-on) + 1 step-20 mutant: 51 slot reserve applied without a downhill neighbour (fib(10) on 1×1 with exactly the 93 free node / var slots its RTL run needs ends in status 2) |

Strong confluence is the test oracle. Any schedule (arbitration, delays, stalls, task/message priority,
initial placement) must produce exactly the same normal form, the same number of interactions and the
same number of live nodes. The fuzzers vary all of these on every run.

### Message traffic of low-parallel programs (steps 11–12)

Step 10 handed *every* REF expansion to a hungry neighbour. On programs with little parallelism
(quicksort, list pipelines, a counter) that spread a sequential chain over the mesh: qsort(40) on 8×8
sent 1.69 messages per interaction (LINK 15,669 / NODE 5,759 / SPAWN 1,932) at 9% utilisation, and
sum(1000) was 1.5× *slower* on any mesh than on one cell. Two changes (SPEC §3 and §5, mirrored in
`omega/fabric.py`; all knobs are configuration inputs, so one build serves every setting):

* **Sender-side threshold + definition hints (step 11).** The loader marks recursion SCCs called
  twice from one template as *fork* (fib, gen/tsum, qs) and every recursion SCC as *rec*. A fork REF
  is always given to a hungry neighbour; a linear-recursion REF only while more than `spawn_k` = 16
  tasks wait locally; a non-recursive one (constructors, arms) while more than `spawn_k2` = 4 wait.
  A plain threshold without hints was rejected: it slows fib(20) 4×4 by 36% at K = 2 and 3.1× at K = 8.
* **Local-first link orientation (step 12).** A var ~ var link may be resolved at either var's owner;
  when one var is local the cell does the exchange itself instead of sending LINK to the other's
  cell. This removes 30–55% of the LINKs and also speeds up fib and the tree sums.
* **Path compression: studied, not implemented.** In a linear net the pointer that caused a
  forwarded LINK is consumed by it and the intermediate var is freed, so there is no source pointer
  left to update. The only forwards a different scheme could save are chains of ≥ 2 forwards:
  ≤ 5.4% of LINKs on 8×8 (`bench/link_forwards.py`). Same-cycle merging of LINKs to one destination
  found 0 opportunities (the outbox drains every cycle). Node migration already moves the local node.

Seed 1, 1024-slot cells, cluster ROM 2×2:1 (`results/bench_msgs.md`; base = step-10 RTL
`results/bench_msgs_base.md`; sweeps and 4-seed means in `results/spawn_sweep.md`):

| program | 8×8 cycles base → new | vs 1×1 | 8×8 msgs/interaction | 8×8 utilisation | 4×4 cycles base → new | 4×4 msgs/int. |
|---|---:|---:|---:|---:|---:|---:|
| qsort(40) | 12,270 → 15,270 (+24%) | 2.81× faster | 1.686 → **0.385** | 9% → 5% | 12,431 → 15,783 | 1.497 → 0.376 |
| list(120) | 10,683 → 9,485 (−11%) | 2.01× faster | 1.788 → **0.404** | 5% → 3% | 10,321 → 9,231 | 1.706 → 0.389 |
| sum(1000) | 44,813 → 28,943 (−35%) | 1.00× (base 0.65×) | 1.066 → **0.022** | 2% → 2% | 44,295 → 28,942 | 1.054 → 0.022 |
| fib(20) | 18,669 → 17,736 (−5.0%) | 39.3× | 0.173 → 0.141 | 64% → 66% | 50,274 → 48,010 | 0.060 → 0.035 |
| treesum(9) | 2,544 → 2,224 (−12.6%) | 22.3× | 0.806 → 0.396 | 42% → 41% | 4,529 → 4,340 | 0.341 → 0.214 |
| treesum_direct(14) | 16,914 → 13,983 (−17.3%) | 37.3× | 0.317 → 0.198 | 59% → 67% | 36,354 → 36,608 | 0.046 → 0.047 |

All three low-parallel programs are below 0.5 messages per interaction on 2×2, 4×4 and 8×8 and no
slower than one cell (sum(1000) on 1×1 needs a 4,096-slot cell: 29,018 cycles vs 28,943 on 8×8). In
step 12 the cost was qsort: on meshes it was 16–27% slower than with step 10's eager spreading,
because its filter chains (lo/hi/app) stayed where they started; step 13 (next section) fixes that. treesum(9)
on 8×8 varies ±20% with the arbitration seed; over seeds 1–4 the mean is 2,374 vs 2,470 for step 10.

### Where the step-19 default gives cycles back, and what progress it guarantees (step 20)

Step 19 left two loose ends: under global memory pressure its default (`+rto=8 +rgrad=3`) is 3.7% slower than
step 18 on treesum(6) 3×3 and gives back about half of the `+rto=8` gain on list(20) 3×2 and fib(12) 6×6;
and it had no argument for *why* it should not livelock. Step 20 finds the cause of the first, keeps the one
cheap fix that is safe (**slot reserve 4 → 1**, new run-time input `+rsv` / `OMEGA_RSV`, `+rsv=4` = step 19
cycle for cycle), and writes the progress argument down with a counterexample (SPEC §7.1).

**A. Cause: the ballast cells stop working.** Under the step-19 rules every homeless task near the room goes to
the room, so the one roomy cell does almost all of the work. treesum(6) 3×3 seed 1 on the fabric model
(`results/s20/diag.py`): the room cell does 2,040 of 2,270 interactions at `+rto=32`, 2,081 at `+rto=8` alone,
and **all 2,270** at the step-19 default; list(20) 3×2: 918 / 849 / 1,037 of ~1,070; fib(12) 6×6: every cell
within 3 hops of the room does 0 interactions under the default and 9–60 each before. The run time is the room
cell's work, so moving ~10% of it back to the 8-free-slot ballast cells is the whole difference. The corner
never gets near its watermark in these runs (it uses at most 244 of 1,024 var slots), so `roomy` never changes
and hysteresis on it cannot matter here.

Which rule takes the work away (fabric model, 20 seeds each, mean cycles; treesum(9) 3×3 = the step-19
livelock set; `results/s20/ftable.md`, `sw1.jsonl`, `sw2.jsonl`, `sw4.jsonl`, `sw6.jsonl`; `perf.py`; knobs below are
fabric-only probes, all off by default; `r32g0` / `r8g0` = `+rto=32 / 8 +rgrad=0`; `rsvN` = reserve N; `rgm0` = rule 1 off,
`rgm2` = rule 1 only after one park; `rg1f1` = rule 1 only when the expansion does not fit even without the reserve;
`rg1d2` / `rsvd2` = rule 1 / reserve only at room distance ≥ 2; `rsvi1` = no reserve in an idle cell; `rg2off` = rule 2 off):

| config | treesum(6) 3x3 (1-20) | list(20) 3x2 (1-20) | fib(12) 6x6 (1-20) | treesum(9) 3x3 (1-20) |
|---|---:|---:|---:|---:|
| r32g0 | 13,160 | 6,353 | 30,577 | **2/20** livelock |
| r8g0 | 12,964 | 6,167 | 32,307 | **19/20** livelock |
| step 19 (`rsv=4`) | 13,624 | 6,943 | 33,706 | 0/20 · 109,507 |
| rsv0 | 13,444 | 5,984 | 33,042 | 0/20 · 109,396 |
| **rsv1 (step 20)** | 13,488 | 6,166 | 33,102 | 0/20 · 109,395 |
| rsv2 | 13,557 | 6,694 | 33,706 | 0/20 · 109,438 |
| rsv3 | 13,624 | 6,943 | 33,706 | 0/20 · 109,507 |
| rgm0 | 13,697 | 7,001 | 33,940 | 0/20 · 109,579 |
| rgm2 | 13,643 | 6,798 | 33,735 | 0/20 · 109,525 |
| rsvi1 | 13,491 | 6,694 | 32,994 | **2/20** livelock |
| rg1f1 | 13,697 | 7,001 | 33,940 | 0/20 · 109,579 |
| rg1d2 | 13,624 | 6,943 | 33,706 | 0/20 · 109,507 |
| rsvd2 | 13,602 | 6,678 | 33,506 | 0/20 · 109,483 |
| rsvi1rg1f1 | 13,445 | 6,140 | 32,994 | **2/20** livelock |
| rg2off | 13,624 | 6,904 | 33,706 | 0/20 · 109,507 |
| rsv1rg2off | 13,488 | 6,124 | 33,102 | 0/20 · 109,395 |
| rsv0rgm0 | 13,497 | 6,520 | 32,912 | **15/20** livelock |
| rsv0rgm0rg2off | 12,964 | 6,167 | 32,307 | **19/20** livelock |

* The **reserve** (rule 3) is most of it on list(20) and fib(12): with 8 free slots a ballast cell cannot
  expand a 5–6-node definition if it must leave 4 free, so every such SPAWN is sent on. Reserve 1 or 0 gives
  back list(20) 6,943 → 6,166 / 5,984 and fib(12) 6×6 33,706 → 33,102 / 33,042, with 0 livelocks.
* Turning off **downhill-at-once** (rule 1, `rgm0` / only after a park `rgm2` / only when nothing fits
  `rg1f1`) or the **downhill escalation** (rule 2, `rg2off`) alone does not help: the parked SPAWN then
  escalates downhill anyway, or the reserve still sends it on.
* treesum(6) needs **all three** off to get back to `+rto=8` (`rsv0rgm0rg2off`: 12,964, the same cycles as
  `+rto=8` alone on all four cases), and that configuration is step 18's round-robin spreading again: it
  livelocks treesum(9) 3×3 19 / 20, and reserve 0 with rule 1 off already does 15 / 20. The spreading that helps
  treesum(6) is the same mechanism that builds treesum(9)'s tree in scattered poor cells (step 19, root cause 1);
  the two cases differ only in how much memory the program needs, which no cell can see locally.
* Rejected: waiving the reserve in an idle cell (`rsvi1`: 2 / 20 livelocks), the reserve only far from the room
  (`rsvd2`: little gain), rule 1 only far from the room (`rg1d2`: no change; near the room the roomy neighbour
  is taken first anyway). "Engage the gradient only when local free < threshold" cannot separate these cases:
  every ballast cell starts with exactly 8 free slots, so any threshold is either "always" or "never".

**Adopted: reserve 1.** With room downhill an expansion still never takes a cell's *last* node or var slot, so a
`NODE` / `PULL` passing through can always be absorbed (the deadlock the reserve was added for, step 19 root
cause 2), but a ballast cell can run one small expansion again.

Livelock sets at the new default (`+rto=8 +rgrad=3 +rsv=1`):

| case (seeds) | model | step 19 (`+rsv=4`) | step 20 (`+rsv=1`) |
|---|---|---:|---:|
| treesum(9) 3×3 (1–20) | fabric | 0/20 | 0/20 |
| treesum(7) 8×8, fib(12) 6×6, qsort(15) 6×6, list(20) 3×2 (21–40 each) | fabric | 0/80 | 0/80 |
| fib(12) 3×3, qsort(15) 4×4, sort(10) 3×3 (1–20 each) | fabric | 0/60 | 0/60 |
| treesum(9) 3×3 (1–30) | RTL | 0/30 | 0/30 (`results/s20/rtl_ts9.jsonl`) |
| treesum(7) 8×8 (1–30) | RTL | 0/30 | 0/30 |
| the other 7 global cases (1–13) | RTL | 0/91 | 0/91 |

Cycles under global memory pressure (RTL, same runs as the step-19 table: seeds 1–13, treesum(7) 8×8 seeds 1–30,
jitter 30%, every run checked against the semantic reducer; `results/s20/rtl1.jsonl`, `rtl_big.py`, `summ.py`):

| case | `+rto=32 +rgrad=0` (step 18) | `+rto=8 +rgrad=0` | step 19 (`+rsv=4`) | **step 20 (`+rsv=1`)** | Δ vs step 19 | Δ vs step 18 |
|---|---:|---:|---:|---:|---:|---:|
| fib(12) 3x3 | 15,190 | 14,951 | 14,916 · 6 msgs | 14,919 · 17 msgs [13] | +0.0% | -1.8% |
| treesum(6) 3x3 | 5,880 | 5,824 | 6,098 · 10 msgs | 6,100 · 56 msgs [13] | +0.0% | +3.7% |
| list(20) 3x2 | 3,592 | 3,021 | 3,236 · 176 msgs | 3,114 · 240 msgs [13] | -3.8% | -13.3% |
| qsort(15) 4x4 | 12,107 | 11,607 | 11,542 · 29 msgs | 11,542 · 29 msgs [13] | +0.0% | -4.7% |
| sort(10) 3x3 | 4,113 | 3,828 | 3,761 · 21 msgs | 3,752 · 27 msgs [13] | -0.2% | -8.8% |
| fib(12) 6x6 | 15,161 | 12,913 | 13,917 · 734 msgs | 13,694 · 880 msgs [13] | -1.6% | -9.7% |
| qsort(15) 6x6 | 12,584 | 11,728 | 11,653 · 33 msgs | 11,653 · 33 msgs [13] | +0.0% | -7.4% |
| treesum(7) 8x8 | 28,003 | 8,436 | 7,685 · 5,359 msgs | 7,545 · 5,399 msgs [30] | -1.8% | -73.1% |

* `+rsv=4` reproduces step 19 exactly on the RTL (treesum(6) 3×3 6,098 and list(20) 3×2 3,236, 13 seeds each).
* Gains: list(20) 3×2 −3.8% and fib(12) 6×6 −1.6% against step 19 (now −13.3% / −9.7% against step 18,
  +3.1% / +6.0% against `+rto=8` alone, which livelocks); the rest within ±0.2%. Messages rise a little where
  work spreads again (treesum(6) 10 → 56, list(20) 176 → 240, fib(12) 6×6 734 → 880), still far under step 18
  (279 / 547 / 2,223).
* **treesum(6) 3×3 stays 3.7% slower than step 18** (6,100 vs 5,880): on the RTL the reserve was not what kept
  the work away, rules 1–2 are, and turning those off brings back the treesum(9) livelock. Kept as known gap 3.
* Without memory pressure nothing changes (the reserve only applies with a downhill neighbour, i.e. with a
  non-roomy cell): identity: 128/128 runs identical to step 15 (cycles, interactions, per-type message counts) (`results/s20/id_4x4.jsonl`, `id_8x8.jsonl`, `idcmp.txt`).

**B. Progress: what the default guarantees and what it cannot** (full text SPEC §7.1).
1. *Safety* holds unconditionally: re-homing work is location free, so a run that ends has the semantic result.
2. *The network cannot deadlock* as long as some cell has a free node slot for each `NODE` / `PULL` it must take:
   XY routing is deadlock free when ejection drains, the head of an ejection port can only block on a
   `NODE` / `PULL` in a cell with no free node slot, every task of such a cell completes or leaves it in bounded
   time (sends never block, homeless work parks for `rto` cycles and leaves after 4 parks), and once the cell has
   nothing else to do rule 4 passes the head on. With room downhill the reserve keeps a cell from reaching that
   state through expansions at all.
3. *Placement is live within the gradient*: while a cell stays roomy, a SPAWN that does not fit within `rgrad`
   hops of it moves to a strictly smaller room distance on every failure and reaches a roomy neighbour in at most
   `rgrad` hops. Farther away it moves round robin (a rotor-router walk, which for a single walker visits every
   cell within O(|E|·D) moves; with the rotors shared by other traffic this is an argument, not a proof).
4. **No completion guarantee, and no cheap local mechanism can give one.** Counterexample
   (fabric model; `results/s20/cex.py`, `cex.jsonl`, `cexdiag.py`): treesum(9) on one cell needs **115** free node / var slots
   (depth first; `minkeep.py`). On 3×3 with 8 free slots in each ballast cell and **200** in the corner (264 in
   total, 2.3× the sequential need) the default stops on **20 / 20 seeds** (so does `+rto=32 +rgrad=0`); with 300 in
   the corner all 20 finish. The stopped state (seed 1: 791 of 18,410 interactions): every pending task is a
   SPAWN (5 queued, 9 parked), no cell has more than 4 free var slots, the corner has 97 free nodes but 2 free
   vars. The parallel order has materialised more than twice the sequential peak, and what is left is
   fragmented below the size of any definition, so **no schedule can continue**: neither a hop budget nor an
   escape network helps, because there is no place to put the work. (At 200 free slots the corner is also below
   the absolute `roomy` watermark of 256, so the gradient never sees it; a lower watermark, 64 / 32, still stops
   5 of 10 seeds.) A real guarantee needs memory-aware admission before the fabric fills (e.g. a global
   low-memory mode that stops giving work away and runs depth first) or spilling to off-fabric memory; both are
   bigger than a step and are listed under next steps. A hop budget would only turn endless bouncing into a quiet
   out-of-memory stop, which status 3 already reports.

**Hardware cost.** None new: `RSV19` becomes the 3-bit run-time input `rsv` shared by all cells (the adders on
the room check already existed). Mutant 51 (reserve applied without a downhill neighbour) is caught by fib(10)
on 1×1 with exactly the 93 free slots its RTL run needs (`results/s20/minkeep_rtl.py`).

### Short retry timeout made safe: room-distance gradient, slot reserve and full-cell pass-on (step 19)

Step 18 left `+rto=8` as a knob: up to 58% faster under global memory pressure, but the fabric model
livelocked more often. Step 19 found why, fixed it, and makes the short timeout the default:
**`+rto=8 +rgrad=3`** (testbench defaults; `OMEGA_RTO` / `OMEGA_RGRAD` for the fabric model and
`omega/rtl.py`). **`+rto=32 +rgrad=0` is step 18 cycle for cycle** (all 24 runs of `results/s18/rto_global.jsonl`
at 32 reproduce exactly on the final RTL: `results/s19/rto_global_old.jsonl`, `rto_global_old2.jsonl`).

**Root cause 1: not a retry storm, but a global out-of-memory reached by ordering.** The livelock case is
global treesum(9) 3×3 (every cell but the far corner left with 8 free node / 8 free var slots). A stuck run
(`results/s19/diag.py`, `traj.py`, `bound.py`, `cq.py`, `exps.py`) ends with the corner's 1,024 var slots
full: 199 vars bound to tree constructors, 58 to unexpanded `gen` leaves, all other cells idle, only SPAWNs
circulating (300k of them), so nothing can ever be expanded again. One cell on its own needs 118 vars at the
peak (depth-first), so the program fits easily; what differs is the order. In a failing run the consumer
(`tsum`) expands 3–8 times in the first 3,000 cycles against ~76 producer (`gen`) expansions; in a
successful one 18–57 against 58–70 (`results/s19/ratio.py`). Parked producer SPAWNs (`gen__a2`, 6 nodes /
6 vars) escalate after 4 short parks and wander round robin into whichever ballast cell happens to fit them,
so the top of the tree is built in scattered poor cells; the consumer arms that must match it there
(`tsum__a3`, 5 / 5) find no room, and the matching consumer tasks end at the *bottom* of the corner's LIFO
stack while new producer work keeps arriving on top. The corner then materialises the whole tree and runs
out of vars. A shorter timeout makes the early wandering faster; rto = 32 hits the same race 2 times in 20.
The RTL reproduces it: global treesum(9) 3×3, seeds 1–30, `+rto=8` stops at ~2,900 of 18,410 interactions
10 times (status 3, cycle limit), `+rto=32` never (`results/s19/rtl_ts9.jsonl`).

**What did not work** (fabric model, treesum(9) 3×3 seeds 1–20 + the global set; `results/s19/fabric_table.md`,
`sweep1.jsonl`, `sweep2.txt`; patch of all probe knobs `results/s19/probe19_fabric_all_knobs.patch`):
per-cell exponential backoff of the retry timer (shift 1–3, reset on success or on any interaction) and
LFSR jitter on the reload: 7–16 livelocks of 20 instead of 19, and the backoff gives back the 8×8 gain
(treesum(7) 8×8 up to 26,190 fabric cycles); escalating later (`OMEGA_ESCN`, step 18): 7 / 20; aging the
LIFO (every k-th pop under pressure takes the oldest task, several gates): consumers run again but memory
grows breadth-first, 3–7 of 10 still livelock (`sweep2.txt`) and finishing runs are up to 50% slower. Retry timing is not the lever; *where* homeless
work goes is.

**The fix.** Each cell registers a 3-bit room distance `rdist` (0 when roomy, else 1 + the neighbours'
minimum, saturating at the run-time cap `rgrad`) and drives it to its neighbours next to `roomy`. Rules 1–3
apply when a neighbour is closer to room (*downhill*), rule 4 whenever `rgrad` ≠ 0:
1. a SPAWN that has no room and no roomy neighbour is forwarded downhill **at once** instead of being parked
   (so producer work goes to the room instead of wandering into poor cells; downhill only after one park:
   8 / 20 livelocks; only escalations downhill: 15 / 20);
2. escalated retries (SPAWN, SWI `NODE`, commutation `PULL`) go downhill instead of round robin;
3. an expansion must leave **4 free node and var slots** (`RSV19`). Root cause 2, found on the RTL once (1)
   was in: with only (1)–(2), global treesum(7) 8×8 stopped 4 times in 13 at `rgrad=3` (once in 3 at `rgrad=7`,
   at 4,565 of 4,586 interactions, few messages). The stuck mesh had a cell on the downhill path with 0 free
   node / 0 free var slots (`results/s19/diag_g7_ts7.txt`): SPAWNs passing through had been expanded there
   because they just fitted, and a cell with no free node cannot take the `NODE` / `PULL` at the head of its
   ejection port, so it blocks for good. The reserve keeps passing work moving downhill.
4. a `NODE` / `PULL` at the ejection head of a cell with **no free node slot at all and nothing else to
   do** is passed on to a roomy neighbour, else downhill, else round robin (a `NODE` whose partner is a
   node goes on as a `PULL`, so the taker asks for the partner and the full cell empties). Root cause 3:
   with (1)–(3), 30 seeds of global treesum(7) 8×8 still stopped twice (seeds 16 and 18, at 4,566 /
   4,551 of 4,586 interactions; `results/s19/rtl_ts7.jsonl`): a cell *more* than `rgrad` hops from the
   room (no downhill neighbour, so no reserve) had expanded to 0 / 0, and the `LINK`s that would have
   freed it were queued behind the blocked `NODE` (head-of-line; `results/s19/diag_rsv_ts7_s16.txt`).
   The same deadlock stops `+rto=8 +rgrad=0` on seed 9 (4,535 of 4,586), so it was there in step 18 at
   the short timeout. Passing the `NODE` on unchanged was not enough (it was migrated straight back by
   the redex rule: 207,337 `NODE` messages on seed 16, still stuck; log of that attempt not kept); as a `PULL` both seeds finish (7,528 / 6,206
   cycles, `results/s19/diag_fwd_ts7_s1*.txt`). Re-homing a node is not an interaction and is location
   free, so the rewrite keeps the result.

Without a downhill neighbour (room more than `rgrad` hops away, or the whole fabric full) rules 1–3 are the
step-10 rule and rule 4 only moves blocked arrivals on, so the overfull cases still end in status 3. All
four rules are off at `rgrad=0`. Cap 3 was chosen over 7 on both models: at 7
cells far from the room all funnel into one corner (RTL fib(12) 6×6 14,785 vs 12,888 cycles at `+rto=8`
alone; fabric fib(12) 6×6 +10%, treesum(7) 8×8 +58%); at 2 the fabric livelocks treesum(9) 3×3 8 / 20 again.

**Livelock rates** (runs that stop without progress; fabric: "no progress for 100,000 cycles", RTL: cycle limit):

| case (seeds) | model | `+rto=32 +rgrad=0` (step 18) | `+rto=8 +rgrad=0` | `+rto=8 +rgrad=3` (step 19) |
|---|---|---:|---:|---:|
| treesum(9) 3×3 (1–20) | fabric | 2/20 | **19/20** | **0/20** |
| list(20) 3×2 (1–20) | fabric | 0/20 | 0/20 | 0/20 |
| treesum(7) 8×8, fib(12) 6×6, qsort(15) 6×6, list(20) 3×2 (21–40 each) | fabric | 1/80 | 2/80 | 0/80 |
| treesum(9) 3×3 (1–30) | RTL | 0/30 | **10/30** | **0/30** |
| treesum(7) 8×8 (1–30) | RTL | 0/30 | 1/30 | 0/30 (rules 1–3 only: 2/30) |
| the other 7 global cases of the cycle table (1–13) | RTL | 0 | 0 | 0/91 |

Fabric: `results/s19/sweep5.jsonl`, `sweep6.jsonl`, `sweep7.jsonl` (final model), `fabric_table.md`; RTL:
`rtl_ts9.jsonl`, `rtl_ts9_fwd.jsonl`, `rtl_big.jsonl`, `rtl_ts7.jsonl`, `rtl_fwd.jsonl` (final RTL).

**Cycles under global memory pressure (RTL, seeds 1–13, treesum(7) 8×8 seeds 1–30, jitter 30%; mean of the runs that finished; every run checked against the semantic
reducer; `bench/rto18_rtl.py`, `results/s19/rtl_big.py`, table `results/s19/table19.py`):**

| case | `+rto=32 +rgrad=0` (step 18) | `+rto=8 +rgrad=0` | `+rto=8 +rgrad=3` (step 19) | Δ new vs 32 | Δ new vs 8/0 |
|---|---:|---:|---:|---:|---:|
| fib(12) 3x3 | 15,190 · 32 msgs [13] | 14,951 · 32 msgs [13] | 14,916 · 6 msgs [13] | -1.8% | -0.2% |
| treesum(6) 3x3 | 5,880 · 279 msgs [13] | 5,824 · 238 msgs [13] | 6,098 · 10 msgs [13] | +3.7% | +4.7% |
| list(20) 3x2 | 3,592 · 547 msgs [13] | 3,021 · 492 msgs [13] | 3,236 · 176 msgs [13] | -9.9% | +7.1% |
| qsort(15) 4x4 | 12,107 · 29 msgs [13] | 11,607 · 29 msgs [13] | 11,542 · 29 msgs [13] | -4.7% | -0.6% |
| sort(10) 3x3 | 4,113 · 27 msgs [13] | 3,828 · 27 msgs [13] | 3,761 · 21 msgs [13] | -8.6% | -1.7% |
| fib(12) 6x6 | 15,161 · 2,223 msgs [13] | 12,913 · 2,178 msgs [13] | 13,917 · 734 msgs [13] | -8.2% | +7.8% |
| qsort(15) 6x6 | 12,584 · 33 msgs [13] | 11,728 · 33 msgs [13] | 11,653 · 33 msgs [13] | -7.4% | -0.6% |
| treesum(7) 8x8 | 28,003 · 8,084 msgs [30] | 8,436 (**1/30 stuck**: seed 9) · 7,898 msgs [30] | 7,685 · 5,359 msgs [30] | -72.6% | -8.9% |

* **Decision: the default becomes `+rto=8 +rgrad=3`.** No run of the new default stopped (livelock column above:
  0 on both models, against 2 / 20 fabric and 0 RTL at `+rto=32`, and 19 / 20 fabric, 10 / 30 + 1 / 30 RTL at
  `+rto=8` alone), and it keeps or beats the short timeout's gain on 5 of 8 cases: treesum(7) 8×8 28,003 →
  7,685 cycles (−72.6%, 30 seeds; `+rto=8` alone 8,436 and one stuck seed), qsort(15) 4×4 / 6×6 −4.7% / −7.4%,
  sort(10) 3×3 −8.6%, fib(12) 3×3 −1.8%.
* **Where it gives something back.** list(20) 3×2 and fib(12) 6×6 keep about half of the `+rto=8` gain
  (−9.9% / −8.2% against `+rto=32`, +7.1% / +7.8% against `+rto=8` alone): homeless work now goes to the room
  instead of being spread round robin over the ballast cells. treesum(6) 3×3 is **3.7% slower than step 18**
  (6,098 vs 5,880): with the room 1–4 hops away, everything funnels to the corner. Known gap 3.
* **Fewer messages everywhere work moves**: treesum(6) 3×3 279 → 10, list(20) 3×2 547 → 176, fib(12) 6×6
  2,223 → 734, treesum(7) 8×8 8,084 → 5,359.
* `+rto=32 +rgrad=0` reproduces step 18 cycle for cycle on the final RTL as well (all 24 runs of
  `results/s18/rto_global.jsonl` at 32: `results/s19/rto_global_old2.jsonl`).

**No change without memory pressure.** With nothing parked and every cell roomy, `rdist` stays 0 and the
timeout is never loaded, so the default changes nothing: all 8 benchmark programs on 4×4 and 8×8, seeds 1–8,
reproduce `results/s15/final_*.jsonl` cycle for cycle with the same message counts (128/128 runs;
`results/s19/id_4x4.jsonl`, `id_8x8.jsonl`).

**Hardware cost.** 3 flip-flops per cell (`rdist`), 4 × 3 bits of neighbour wires, a 4-way 3-bit minimum,
four 3-bit comparators, a saturating increment, two adders on the room check and, for rule 4, one more
branch in the pick logic that re-addresses the ejection head into the outbox (a 2-bit kind rewrite and
two 4-bit coordinate muxes, reusing the existing roomy / downhill / round-robin selection): roughly
60–100 GE of logic per cell (estimate, not synthesised), under 0.1% of the step-8 cell's standard-cell logic; no memory. `rgrad` is a 3-bit run-time input
shared by all cells.

### Retry-slot timeout as a knob: faster under pressure, but more livelock (step 18)

*(Superseded in step 19: the livelock is fixed and `+rto=8` is the default together with `+rgrad=3`.)*

Step 17's probe showed that a global-pressure run spends most of its time parked, so the timeout itself was
swept. It is now a run-time input of the cell (`rto_m1`, testbench `+rto=`, `OMEGA_RTO` for the fabric model
and `omega/rtl.py`), loaded into the same 6-bit `rs_tm`; no other RTL change. **The default stays 32**
(step 17's behaviour, cycle for cycle), for the reason below.

RTL, Verilator, seeds 1–3, jitter 30%, every cell but the far corner left with 8 free node / 8 free var
slots (the five global-pressure cases of `tests/test_mempress.py` plus three bigger meshes;
`bench/rto18_rtl.py` → `results/s18/rto_global.jsonl`; every run checked against the semantic reducer):

| case | `+rto=32` (default) | `+rto=16` | `+rto=8` | Δ 8 vs 32 |
|---|---:|---:|---:|---:|
| fib(12) 3×3 | 15,205 | 15,027 | 14,969 | −1.6% |
| treesum(6) 3×3 | 5,866 | 5,841 | 5,843 | −0.4% |
| list(20) 3×2 | 3,606 | 3,109 | 2,969 | −17.6% |
| qsort(15) 4×4 | 12,108 | 11,785 | 11,595 | −4.2% |
| sort(10) 3×3 | 4,114 | 3,927 | 3,827 | −7.0% |
| fib(12) 6×6 | 15,589 | 12,925 | 12,888 | −17.3% |
| qsort(15) 6×6 | 12,572 | 12,013 | 11,758 | −6.5% |
| treesum(7) 8×8 | 21,407 | 11,534 | 8,926 | **−58.3%** |

* **Faster on every case.** A parked retry costs no engine cycles, and with a short timeout the 4th park
  (escalation: round-robin forwarding) comes after 32 instead of 128 cycles, so work leaves cramped cells
  sooner (treesum(7) 8×8 parks 14,917 times per run at 32 cycles).
* **No effect without memory pressure.** Programs that never park run cycle for cycle as in step 15 at
  `+rto=8`: all 8 benchmark programs × seeds 1–2 on 4×4 and 8×8 reproduce `results/s15/final_*.jsonl`
  exactly (`results/s18/id_*.jsonl`). At `+rto=8` units 42/42, programs 315/315, step-14 cross-check 90/90,
  fuzz 600/600, security 420/420 and the RTL half of the memory-pressure suite passed.
* **Why it is not the default: livelock.** The fabric model's memory-pressure case global list(20) 3×2
  (seed 33) stops with "no progress for 100,000 cycles" at 8 (fine at 4, 12, 16, 32). Over seeds 1–20
  (`results/s18/livelock_rto*.txt`): list(20) 3×2 livelocks 0 / 1 / 0 / 0 times at 8 / 16 / 12 / 32, and the
  near-overfull treesum(9) 3×3 19 / 5 / 10 / 2 times. Early escalation is both the gain and the risk: keeping
  escalation at ≈128 cycles (fabric knob `OMEGA_ESCN`: escalate on the 16th park at 8 cycles) removes most of
  the gain (treesum(7) 8×8 back to 18,759 fabric cycles) and still livelocks treesum(9) 3×3 7 / 20 times. The
  RTL did not livelock in any run above, but it has no progress detector, only a cycle limit.
* Taking the gain safely needs the progress guarantee that known gap 3 already asks for (a forwarded SPAWN
  that cannot bounce forever, e.g. a hop budget or forwarding toward room); until then `+rto` is a knob.

### Room-distance gradient under global memory pressure: probe rejected (step 17)

Next step 3 on the fabric model (`results/s16/rgrad17.py`, patch `results/s16/probe17_rgrad.patch`; the five
global-pressure cases of `tests/test_mempress.py` plus fib(12) 6×6, qsort(15) 6×6, treesum(7) 8×8, every cell
but the far corner left with 8 free node / 8 free var slots, seeds 1–4, jitter 0.1). Each cell registers a
room distance `rd` (0 when roomy, else 1 + the neighbours' minimum, capped at G), the analogue of step 14's
hunger distance.

* **Escalated retries go downhill instead of round robin** (G = 8): far fewer messages where work moves at all
  (treesum(7) 8×8 7,288 → 2,755, fib(12) 6×6 1,944 → 195, treesum(6) 3×3 330 → 114), but *slower*: treesum(7)
  8×8 18,046 → 20,199 cycles (+12%, G = 15: +35%), fib(12) 6×6 31,088 → 35,629 (+15%), treesum(6) 3×3 +4.5%;
  list(20) 3×2 −3.9%; the rest unchanged. Round robin spreads work over the ballast cells, which still have a
  few free slots each, and that parallelism is worth more than reaching the one roomy corner quickly.
* **No parking when a downhill neighbour exists** (expansions only, or also the SWI / commutation offloads):
  sort(10) 3×3 −5%, qsort(15) 4×4 / 6×6 −2.5% / −2.9%, but list(20) 3×2 +7%, fib(12) 6×6 +15%, and the fabric
  **livelocks** (no progress for 100,000 cycles) on treesum(7) 8×8 (expansions only, G = 8) and list(20) 3×2
  (all three sites): work that is sent downhill without waiting bounces between cells whose rd changes
  under it. Kept: step 10's park-and-escalate.

Most of a global-pressure run is spent parked (fib(12) 3×3 needs 36,346 cycles with only 32 messages): the
work fits in the ballast cells' few free slots and waits for slots to be freed, rather than moving to the room.

### Two fabric probes, both rejected (step 16)

Screened on the fabric model only (arbitration seeds 1–4, step-15 defaults, `bench/probe15.py`); neither
reached the RTL. Raw output: `results/s16/`.

* **Dynamic locality test for the fork deque (next step 5).** Idea: let a data-walking fork task (treesum's
  `tsum`) onto the deque, but give it only when the structure it walks has already left the cell. At push
  time the test never fires: in all 796 `tsum` pushes of treesum(9) 8×8 seed 1, field 0 of the `CON`
  argument is a *local, still unbound* var (the tree arrives later from `gen`), so a push-time test equals
  step 15's static bit. Moving the test to give time (task on the deque, give only if the var is bound to a
  remote node, or also when unbound) is worse than step 15 everywhere it changes anything: treesum(9) 8×8
  4,120 → 5,410 / 4,282 cycles (0.421 → 0.466 / 0.449 msgs/int), 4×4 7,972 → 9,279 / 8,828; letting the
  stream-fed qsort forks in as well: qsort(40) 4×4 21,534 → 22,819 cycles, 8×8 20,599 → 21,471. Kept: the
  static bit 59 of step 15.
* **SPAWN carries the partner node (next step 6).** When a REF ~ node redex is handed to a neighbour and the
  node lives at the sender, send the node itself (an ordinary NODE message whose link partner is the REF;
  the receiver re-forms the redex and expands it locally, never re-giving it) instead of SPAWN(ref, node
  pointer). Nearly every spawned partner is a `CON` holding the return wire as a local var, so shipping it
  turns the expansion's result wire into a remote one. Mixed result, mean of 4 seeds (cycles, step 15 →
  shipped): treesum(9) 8×8 4,120 → 3,696 (−10%, 0.421 → 0.384 msgs/int), sort(20) 4×4 12,152 → 11,060 (−9%),
  higher(100) 4×4 −2%; but qsort(40) 4×4 / 8×8 +6% / +7%, list(120) 4×4 / 8×8 +10% / +16% (0.52 → 0.57
  msgs/int), fib(16) 8×8 +13%. Restricting it to partners with no local-var aux port never fires (every
  partner has one). No static class separates the winners from the losers (fib and treesum's `gen` are both
  numeric forks with a `CON(n, ret)` partner), so it was not taken to RTL (`results/s16/probe16b_ship.patch`).

### Data-walking forks stay off the fork deque (step 15)

Step 14 raised treesum(9) on 8×8 from 0.431 to 0.526 messages per interaction (target < 0.5). Per-kind RTL
counts, 8 seeds (`results/s15/ref14/`: `+s14=0` and step 14's bit 59 re-run on the same binary, which
reproduces `results/s14/final_8x8.jsonl` cycle for cycle):

| treesum(9) 8×8, mean of 8 seeds | LINK | NODE | SPAWN | total | oldest-fork gives | msgs/int |
|---|---:|---:|---:|---:|---:|---:|
| step 13 (`+s14=0`) | 4,116 | 2,538 | 1,280 | 7,934 | – | 0.431 |
| step 14 | 5,049 | 2,969 | 1,666 | 9,684 | 1,543 | 0.526 |
| **step 15** | 4,325 | 2,825 | 1,433 | **8,583** | 909 | **0.466** |

* **Root cause: gives of `tsum` tasks.** In mode 2 the deque took every fork definition that is not
  stream-fed, and treesum's fork SCCs are `gen` (builds the tree) *and* `tsum` (walks it). A `tsum` task is
  `REF ~ CON(tree, ret)`; giving the oldest one hands the walk to a neighbour while the tree it matches on
  stays at the giver, so the first match step goes back as a LINK, the tree node migrates (NODE), and so on
  down the subtree, plus the result wire. Leaving `tsum` off the deque removes 634 of the 1,543 gives and
  1,101 of the 1,750 extra messages (≈ 1.7 messages per `tsum` give). The other candidates do not show up:
  a give is never retried (it happens only with outbox room and a hungry neighbour; otherwise the task is
  just popped later), and the deque push / pop never leaves the cell. The remaining +649 messages over
  step 13 come from `gen` gives: those subtrees are built on the receiver, and part of the walk follows them.
* **Fix: a narrower directory bit 59 (loader only, no RTL change).** A fork SCC is *data-walking* when one
  of its templates takes its first argument apart as a Scott value (the root's argument var meets a CON node
  in a template redex: treesum's `tsum`, `qs`); a numeric fork switches or computes on its argument (fib,
  gen, the direct tsum). Bit 59 now marks forks that are neither stream-fed nor data-walking. The RTL reads
  the bit into the same per-cell hint vector as in step 14, so the cell, its area and its timing are
  unchanged; `OMEGA_DQF_DATA=1` (fabric model and `omega/rtl.py`) restores step 14's bit. Screened first on
  the fabric model (`bench/probe15.py`: treesum(9) 8×8 0.454 → 0.417, 4×4 0.147 → 0.107 msgs/int).
  `tests/test_programs.py` checks the bit for all 9 programs.

RTL, Verilator, arbitration seeds 1–8, default configuration (`results/s15/final_*.jsonl`, `ts_8x8.jsonl`,
`bench/table15.py` → `results/s15/table15.md`; every run checked against the semantic reducer):

| program | mesh | step 14 cycles mean (sd / range) | **step 15 cycles mean (sd / range)** | Δ mean | step 14 msgs/int | **step 15 msgs/int** |
|---|---|---:|---:|---:|---:|---:|
| qsort(40) | 4×4 | 11,454 (801 / 2,345) | **11,454** (801 / 2,345) | 0 | 0.390 | **0.390** |
| list(120) | 4×4 | 8,396 (541 / 1,576) | **8,396** (541 / 1,576) | 0 | 0.389 | **0.389** |
| sum(1000) | 4×4 | 28,952 (22 / 75) | **28,952** (22 / 75) | 0 | 0.022 | **0.022** |
| sort(20) | 4×4 | 5,988 (207 / 618) | **5,988** (207 / 618) | 0 | 0.306 | **0.306** |
| higher(100) | 4×4 | 7,633 (226 / 728) | **7,633** (226 / 728) | 0 | 0.330 | **0.330** |
| fib(20) | 4×4 | 46,272 (402 / 1,208) | **46,272** (402 / 1,208) | 0 | 0.025 | **0.025** |
| treesum(9) | 4×4 | 3,970 (149 / 397) | **3,994** (152 / 481) | +0.6% | 0.167 | **0.159** |
| treesum_direct(14) | 4×4 | 35,205 (162 / 398) | **35,205** (162 / 398) | 0 | 0.021 | **0.021** |
| qsort(40) | 8×8 | 10,844 (816 / 2,054) | **10,844** (816 / 2,054) | 0 | 0.405 | **0.405** |
| list(120) | 8×8 | 8,406 (195 / 486) | **8,406** (195 / 486) | 0 | 0.403 | **0.403** |
| sum(1000) | 8×8 | 28,962 (35 / 92) | **28,962** (35 / 92) | 0 | 0.022 | **0.022** |
| sort(20) | 8×8 | 6,054 (186 / 523) | **6,054** (186 / 523) | 0 | 0.304 | **0.304** |
| higher(100) | 8×8 | 7,800 (98 / 320) | **7,800** (98 / 320) | 0 | 0.348 | **0.348** |
| fib(20) | 8×8 | 16,626 (1,199 / 3,691) | **16,626** (1,199 / 3,691) | 0 | 0.156 | **0.156** |
| treesum(9) | 8×8 | 2,255 (209 / 522) | **2,126** (173 / 521) | **−5.7%** | 0.526 | **0.466** |
| treesum_direct(14) | 8×8 | 12,846 (527 / 1,217) | **12,846** (527 / 1,217) | 0 | 0.209 | **0.209** |

* treesum(9) 8×8: below 0.5 msgs/interaction again and 5.7% faster than step 14 (11.2% faster than step
  13's 2,395). Every program whose bit 59 did not change (all but treesum) runs cycle for cycle as in step 14,
  so the step-14 gains on fib and treesum_direct are kept exactly. treesum(9) on 4×4 is +0.6% (24 cycles,
  within one seed's spread; range 3,777–4,258) at fewer messages (0.167 → 0.159).

### Fork deque and oldest-fork give (step 14)

On 8×8 the fork programs (fib, treesum, treesum_direct) had a long, seed-dependent tail: the task stack is
a pure LIFO, so a hungry neighbour received the *newest* (small, deep) fork task while the big shallow
subtrees sat at the bottom of a few busy cells and ran serially. The fabric-model study
(`results/var/REPORT.md`, branch `explore-variance`) proposed s14c: a 4-entry fork deque per cell from which
a starving neighbour takes the *oldest* fork task, plus a governor that relaxes when a neighbour starves
(nb5l1). Step 14 builds it into the RTL (SPEC §5 "Fork deque and oldest-fork give"; the fabric model has the
same switch, `OMEGA_S14` / `Fabric(s14=)`):

* **Fork deque (per cell, 4 × 128 b).** A pushed task that is a ready `REF ~ x` redex of a fork definition
  (the step-11 fork bit, `x` a NUM / OPR / CON / SWI of the same owner) goes on the deque while it has room,
  every other task on the stack. The hint is a per-cell flip-flop vector (one bit per definition, written
  with the directory), so the classification needs no extra directory read. Pick order: with a hungry
  neighbour, outbox room and ≥ 2 waiting tasks, the **oldest** fork task, which then takes the unchanged
  step-11 path in S_LINK (counted as an interaction, SPAWN to the hungry neighbour); else the stack top;
  the **newest** fork task only when the stack is empty. `hungry`, quiescence and the spawn thresholds
  count stack + deque.
* **Mode 2 (default): only fork definitions that are not stream-fed.** With every fork definition on the
  deque (mode 1, the fabric study's s14c) qsort(40) got slower: +4.9% on 4×4 and +7.2% on 8×8 (8 / 4 seeds).
  Its fork tasks carry partitions that `lo` / `hi` are still emitting element by element, and handing the
  oldest one away moves the consumer away from its producers. The loader now marks directory **bit 59** on
  fork definitions whose SCC calls no producer recursion (fib, gen, tsum: yes; qsort: no), and mode 2 puts
  only those on the deque. `+s14=0` is step 13 cycle for cycle, `+s14=1` the s14c classification.
* **Governor nb5l1: implemented as a knob, off by default.** `+govnb=k` relaxes one level at epoch end when
  a neighbour is hungry and the cell sent ≤ k/4 × the budget, `+govl0` sets the reset level. On the RTL nb5l1
  (k = 5, reset level 1) speeds qsort up (4×4 −4.7%, 8×8 −1.7%) but slows list(120) (+4.8% / +9.5%) and
  higher(100) (+9.8% / +5.5%, 4×4 at 0.52 msgs/interaction); k = 3 with reset level 2 is a wash (qsort
  −1.7% / +2.7%, list +2.3% / +0.2%). The RTL engine is about twice as fast per interaction as the fabric
  model, so on these low-utilisation meshes a neighbour is almost always hungry and the relax fires
  nearly every epoch. Default k = 0, reset level 2: the step-13 governor (known gap 12). Tuning data:
  `results/s14/tune*_4x4.jsonl`, `tune*_8x8.jsonl` (`bench/tune14.py`, `bench/tune14_table.py`).

RTL, Verilator, arbitration seeds 1–8, default configuration (step 13 = `+s14=0`, same binary; every run
checked against the semantic reducer: readback and interaction count; `results/s14/final_*.jsonl`,
`bench/table14.py` → `results/s14/table14.md`):

| program | mesh | step 13 cycles mean (sd / range) | **step 14 cycles mean (sd / range)** | Δ mean | Δ sd | step 13 msgs/int | **step 14 msgs/int** |
|---|---|---:|---:|---:|---:|---:|---:|
| qsort(40) | 4×4 | 11,454 (801 / 2,345) | **11,454** (801 / 2,345) | 0 | 0 | 0.390 | **0.390** |
| list(120) | 4×4 | 8,396 (541 / 1,576) | **8,396** (541 / 1,576) | 0 | 0 | 0.389 | **0.389** |
| sum(1000) | 4×4 | 28,952 (22 / 75) | **28,952** (22 / 75) | 0 | 0 | 0.022 | **0.022** |
| sort(20) | 4×4 | 5,988 (207 / 618) | **5,988** (207 / 618) | 0 | 0 | 0.306 | **0.306** |
| higher(100) | 4×4 | 7,633 (226 / 728) | **7,633** (226 / 728) | 0 | 0 | 0.330 | **0.330** |
| fib(20) | 4×4 | 49,050 (863 / 2,272) | **46,272** (402 / 1,208) | −5.7% | −53% | 0.045 | **0.025** |
| treesum(9) | 4×4 | 4,243 (232 / 689) | **3,970** (149 / 397) | −6.4% | −36% | 0.171 | **0.167** |
| treesum_direct(14) | 4×4 | 36,690 (560 / 1,634) | **35,205** (162 / 398) | −4.0% | −71% | 0.045 | **0.021** |
| qsort(40) | 8×8 | 10,844 (816 / 2,054) | **10,844** (816 / 2,054) | 0 | 0 | 0.405 | **0.405** |
| list(120) | 8×8 | 8,406 (195 / 486) | **8,406** (195 / 486) | 0 | 0 | 0.403 | **0.403** |
| sum(1000) | 8×8 | 28,962 (35 / 92) | **28,962** (35 / 92) | 0 | 0 | 0.022 | **0.022** |
| sort(20) | 8×8 | 6,054 (186 / 523) | **6,054** (186 / 523) | 0 | 0 | 0.304 | **0.304** |
| higher(100) | 8×8 | 7,800 (98 / 320) | **7,800** (98 / 320) | 0 | 0 | 0.348 | **0.348** |
| fib(20) | 8×8 | 18,617 (896 / 2,636) | **16,626** (1,199 / 3,691) | **−10.7%** | +34% | 0.147 | **0.156** |
| treesum(9) | 8×8 | 2,395 (272 / 775) | **2,255** (209 / 522) | −5.8% | −23% | 0.431 | **0.526** |
| treesum_direct(14) | 8×8 | 15,265 (1,146 / 2,599) | **12,846** (527 / 1,217) | **−15.8%** | −54% | 0.226 | **0.209** |

* **Fork programs: faster and steadier.** treesum_direct(14) 8×8 −15.8% (range 2,599 → 1,217), fib(20) 8×8
  −10.7%, treesum(9) −5.8% / −6.4% with sd −23% / −36%; on 4×4 every fork program's sd halves or better.
  4×4 → 8×8 speed-up: fib 2.63× → 2.78×, treesum_direct 2.40× → 2.74×. The step-13 rows for seeds 1–4
  equal `results/step13_table.md` (e.g. qsort 8×8 10,742, treesum(9) 8×8 2,374).
* **Producer and strict programs run cycle for cycle as in step 13** (qsort's fork is stream-fed, list /
  sort / higher / sum have no fork definition), so no program is slower on any seed.
* **What the RTL does not reproduce from the fabric study:** treesum(9) 8×8 sd drops 23% instead of 59%,
  fib(20) 8×8 sd *rises* (896 → 1,199, range 2,636 → 3,691: 14,749–18,440, every seed below the step-13
  mean of 18,617), and treesum(9) 8×8 sends 0.526 instead of 0.431 messages per interaction
  (more gives of `tsum` tasks whose tree lives at the giver: the receiver pulls the nodes after it).
* **Hardware cost (estimate, not synthesised: yowasp-yosys does not fit the sandbox).** Per cell: fork
  deque 4 × 128 b + 3-bit count, two 256-bit hint vectors (bit 56 for mode 1, bit 59 for mode 2; mode 2
  alone needs one), i.e. ≈ 1,030 flip-flops; three hint look-ups (256:1 mux each) and fork classifiers for
  the three task pushes per cycle, push compaction (3 × 130 b), deque shift / insert muxes, two more
  sources in the task pick mux, and one constant-multiply comparator in the governor epoch logic. With
  Nangate45 DFF_X1 / MUX2_X1 areas that is roughly 11,000–13,000 µm², ≈ 8% of the 150,915 µm² step-8
  standard-cell part of a cell (≈ 2% of the cell with its memories). The fabric study's "< 1%" assumed
  72-bit entries; storing `{REF label, owner, x}` (76 b) instead of two full ports would cut the deque by
  40%. The pick mux gains two inputs on the engine's next-state → read-ahead path, which is the step-8
  critical path; its effect on Fmax is not measured.

### Producer recursions and an adaptive message budget (step 13)

Step 12 held every linear recursion back until more than 16 tasks waited, which kept sum(1000) as fast
as one cell but left qsort's filters and its input generator where they started: qsort(40) on 8×8 was
24% slower than with step 10's eager spreading. Step 13 asked for thresholds that adapt to the
measured granularity of each definition. What the measurements showed (`results/gran13_probes.md`):

* **Granularity per definition does not separate the cases that matter.** A handed-out job almost
  never runs where it lands: its root meets a partner that lives at the sender and migrates straight
  back (≈ 1 NODE per job, ≈ 0 interactions at the receiver). The job of the strict counter `sum` and
  that of the list generator `rnd` look the same at the receiver, yet giving `rnd` makes qsort faster
  *and* cheaper (fabric ablation: −14% cycles, msgs/interaction 0.43 → 0.41), while giving `sum` only
  adds a hop to its critical path.
* **Two adaptive per-definition schemes were built and rejected** (fabric model, code kept in
  `bench/experiments/`): 2-bit run-length counters (positive feedback: once relaxed, a strict chain
  stays longer at each receiver and learns "coarse"; sum 8×8 +12% cycles, 0.05 → 0.27 msgs/int) and
  data-affinity counters that credit a job when consumers migrate to the data it left behind (neutral
  start: nothing gets sampled; optimistic start: every fresh cell on a chain's path relaxes sum too).

What was built (SPEC §5 "Producer recursions and the message-budget governor", mirrored in
`omega/fabric.py`; all knobs are mesh configuration inputs, one build serves every setting):

* **Producer hint (loader, directory bit 58).** A linear recursion is a *producer* when its SCC calls
  a non-recursive definition outside the SCC (a constructor or a lifted arm): it emits a data
  structure piece by piece (rnd, lo, hi, app, range, map, insert). Its consumer can work on the head
  while the tail is being made, and the pieces stay spread over the cells that made them. Strict
  recursions (sum, fact, check, lsum, a fold into an operator) keep `spawn_k` = 16. Fork and
  non-recursive definitions are unchanged, so fib and both tree sums run cycle for cycle as in step 12.
* **Message-budget governor (per cell, adaptive).** A producer REF is given while more than `kp_eff`
  tasks wait. A 3-bit level (reset 2) selects `kp_eff` = 0 / 2 / 4 / 8 / 16; after every 32
  interactions the cell compares the messages it sent in that epoch with the budget `gov_b` = 30 per
  100 interactions: above it, one level tighter; below half of it, one level looser. With
  `+govb=0` the fixed `spawn_kp` (default 4) is used instead. Cost per cell: 17 flip-flops, a copy of
  the interaction counter and two constant comparisons; the decision stays in S_LINK.

RTL, Verilator, mean of arbitration seeds 1–4 (`results/s13_*.jsonl`, `bench/sweep13.py`,
`bench/table13.py`; step 12 = `spawn_kp` = 16, which reproduces the step-12 cycle counts exactly):

| program | mesh | step 12 cycles | **step 13 cycles** | change | step 12 msgs/int | **step 13 msgs/int** | util 12 → 13 | step 13 vs 1×1 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| qsort(40) | 2×2 | 18,318 | **15,448** | −15.7% | 0.300 | **0.295** | 64% → 77% | 2.78× |
| qsort(40) | 4×4 | 15,286 | **11,789** | −22.9% | 0.377 | **0.390** | 20% → 26% | 3.64× |
| qsort(40) | 8×8 | 15,006 | **10,742** | −28.4% | 0.382 | **0.403** | 5.0% → 7.0% | 3.99× |
| list(120) | 2×2 | 9,947 | **10,016** | +0.7% | 0.290 | **0.341** | 52% → 52% | 1.90× |
| list(120) | 4×4 | 9,313 | **8,162** | −12.4% | 0.403 | **0.387** | 14% → 16% | 2.33× |
| list(120) | 8×8 | 9,301 | **8,410** | −9.6% | 0.413 | **0.403** | 3.5% → 3.9% | 2.26× |
| sum(1000) | 2×2 / 4×4 | 28,982 / 28,944 | **28,982 / 28,944** | 0 | 0.022 | **0.022** | 24% / 6.1% | 1.00× |
| sum(1000) | 8×8 | 28,940 | **28,940** | 0 | 0.022 | **0.022** | 1.5% | 1.00× |
| sort(20) | 2×2 | 7,800 | **6,791** | −12.9% | 0.244 | **0.284** | 45% → 52% | 1.92× |
| sort(20) | 4×4 | 7,292 | **5,910** | −19.0% | 0.226 | **0.308** | 12% → 15% | 2.21× |
| sort(20) | 8×8 | 7,292 | **6,004** | −17.7% | 0.226 | **0.310** | 3.0% → 3.6% | 2.17× |
| higher(100) | 2×2 | 7,668 | **7,420** | −3.2% | 0.297 | **0.291** | 43% → 44% | 1.65× |
| higher(100) | 4×4 | 8,027 | **7,605** | −5.3% | 0.396 | **0.320** | 10% → 11% | 1.61× |
| higher(100) | 8×8 | 8,132 | **7,780** | −4.3% | 0.418 | **0.347** | 2.6% | 1.58× |
| fact(20) | 2×2 / 4×4 / 8×8 | 596 / 596 / 596 | **596 / 596 / 596** | 0 | 0.019 | **0.019** | – | 1.00× |
| fib(20) | 8×8 | 18,550 | **18,550** | 0 | 0.146 | 0.146 | 63% | – |
| treesum(9) | 8×8 | 2,374 | **2,374** | 0 | 0.419 | 0.419 | 39% | – |
| treesum_direct(14) | 8×8 | 15,057 | **15,057** | 0 | 0.224 | 0.224 | 63% | – |

* **qsort(40) on 8×8: 10,742 cycles, 12% faster than step 10 (12,270 seed 1 / 12,393 mean) at 0.40
  instead of 1.69 messages per interaction.** Every low-parallel program stays below 0.5 messages per
  interaction and no slower than one cell on 2×2, 4×4 and 8×8. All 8×8 rows are measured with the default
  governor (`gov_b` = 30), seeds 1–4 (sum, sort, higher, fact on 8×8: `results/s13_8x8_gap.jsonl`; full table
  `results/step13_table.md`). sum(1000) and fact(20) give the same cycle count as step 12 on every seed (strict
  recursions, no producer REF); 1×1 is 29,018 / 598 cycles. Highest single-seed 8×8 msgs/interaction:
  sort 0.319, higher 0.349.
* Pareto choice for the producer threshold (8×8 means): fixed `spawn_kp` = 2: qsort 10,015 / 0.532
  (over budget); fixed 4: 10,472 / 0.484 (seed 3 at 0.496, no margin); **governor 30: 10,742 / 0.403
  (default)**; governor 40: 10,749 / 0.427; governor 60: 10,582 / 0.512; fixed 8: 12,807 / 0.419;
  fixed 16 (step 12): 15,006 / 0.382. The governor costs up to 9% on qsort 4×4 against the fixed 4
  (11,789 vs 10,765) and buys a constant ≈ 0.40 msgs/interaction on every mesh.
* fib(20), treesum(9) and treesum_direct(14) have no producer definitions and run cycle for cycle as in
  step 12 (every seed identical).

### Retry slot and global memory pressure (step 10)

Before step 10 a cell short of slots pushed the failed rule (or SPAWN) back on its LIFO task stack and
popped it again the next cycle, starving the very tasks that could free memory; a SPAWN without a roomy
neighbour went round robin. A ballast case where the room is two or more hops away hung
(`global list(20) 3×2`: step-9 RTL status 3 after 786 of 1,069 interactions; the fabric model also
livelocked). Now (SPEC §5 "Retry slot and global pressure", mirrored in `omega/fabric.py`):

* **One non-LIFO retry slot per cell** with a 32-cycle timeout: memory-pressure retries park there,
  the engine keeps draining its stack and messages, and the parked entry is retried before the stack
  when the timer expires. A parked entry keeps the cell non-idle and non-hungry.
* **No blind round-robin SPAWN** while the slot can hold it: without room and without a roomy
  neighbour a SPAWN parks.
* **Escalation**: the 4th consecutive park of the same retry moves the work anyway — SPAWN round robin,
  SWI node as NODE, commutation node as PULL to the next neighbour (roomy neighbours still win first).
  Work diffuses through partly full cells toward room several hops away.
* Result: all 5 global-pressure cases pass on semantic / fabric / RTL (step-9 RTL: 4 / 5).
* Still a gap: a *globally* full fabric (overfull cases) ends in status 3 as before, and escalated
  SPAWNs still bounce (treesum(9) on a 2×2 fabric with 24 free slots per cell: ~600k SPAWN messages in
  300k cycles, same as step 9). No throttling or off-fabric spill yet.
* No effect on the benchmarks: no cell runs out of memory there. Re-run on the step-10 RTL, fib(20),
  treesum_direct(14), treesum(9) on 1×1, 2×2, 4×4 give exactly the v4 cycle counts (table below).
  8×8 was not re-run in this step (its Verilator build exhausted the sandbox's 8 GB); its cells peak at
  ≤ 91 nodes of 1,024, so the retry slot is never used there.

### v4 engine (step 9): 2.36 cycles per interaction

Three changes to `rtl/omega_cell.sv` (SPEC §5.1, §5.4), mirrored in the fabric model:

* **Wide EXPAND**: the node RAM and the var RAM get a second write port, and an expansion writes two
  template entries (nodes *i*, *i*+1, var tags *i*, *i*+1, redexes *i*, *i*+1) per cycle. Cluster ROM
  words now hold four entries (512 b; definitions padded to a multiple of four), so one grant still
  feeds two EXPAND cycles.
* **Commutation one cycle shorter**: the rule cycle writes two node slots; the remaining two copies
  and the four fresh var tags drain in one `S_WQ` cycle (2 + 3 instead of 2 + 4).
* **Var-hop unit (VHU)**: substitution chains (local var links) are followed by a small second engine
  on its own var read port and var write port 2, while the main engine picks its next task. It stalls
  when the main engine's link names the same var slot, so var exchanges stay atomic.
* Fix found by the regression: a VHU step that frees a var waits for room in the free-var cache (a
  treesum(7) 2×2 fuzz schedule overflowed it and hung; it now passes with 4,586 interactions).

`python3 bench/bench.py --8x8 --progs fib:20,treesum_direct:14,treesum:9 --tag v4` →
`results/bench_v4.{json,md}` (all columns there). Step-7 default (2×2 cluster, 1 port,
`results/bench_c2x2p1.json`) against v4 in the same configuration; cycles/interaction is mesh cycles ÷
interactions (on 1×1 it is the engine's own cost per interaction):

| program | mesh | step 7 cycles | step 7 cycles/interaction | **v4 cycles** | **v4 cycles/interaction** | change | v4 speed-up vs 1×1 | v4 cell utilisation |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| fib(20) | 1x1 | 1,006,974 | 3.41 | **697,478** | **2.36** | -30.7% | 1.00x | 100% |
| fib(20) | 2x2 | 269,881 | 0.91 | **183,174** | **0.62** | -32.1% | 3.81x | 98% |
| fib(20) | 4x4 | 70,938 | 0.24 | **50,274** | **0.17** | -29.1% | 13.87x | 90% |
| fib(20) | 8x8 | 25,635 | 0.09 | **18,669** | **0.06** | -27.2% | 37.36x | 64% |
| treesum_direct(14) | 1x1 | 753,632 | 3.07 | **521,600** | **2.12** | -30.8% | 1.00x | 100% |
| treesum_direct(14) | 2x2 | 211,721 | 0.86 | **138,238** | **0.56** | -34.7% | 3.77x | 99% |
| treesum_direct(14) | 4x4 | 53,077 | 0.22 | **36,354** | **0.15** | -31.5% | 14.35x | 96% |
| treesum_direct(14) | 8x8 | 19,492 | 0.08 | **16,914** | **0.07** | -13.2% | 30.84x | 59% |
| treesum(9) | 1x1* | 71,590 | 3.89 | **49,536** | **2.69** | -30.8% | 1.00x | 100% |
| treesum(9) | 2x2 | 19,306 | 1.05 | **13,967** | **0.76** | -27.7% | 3.55x | 95% |
| treesum(9) | 4x4 | 6,245 | 0.34 | **4,529** | **0.25** | -27.5% | 10.94x | 80% |
| treesum(9) | 8x8 | 3,195 | 0.17 | **2,544** | **0.14** | -20.4% | 19.47x | 42% |

* One cell: **3.41 → 2.36 cycles per interaction** on fib(20) (−31%), 3.07 → 2.12 on
  treesum_direct(14). Every mesh size gains 27–35% up to 4×4.
* 8×8 gains less (−13% to −27%): the mesh is not saturated (42–64% utilisation), so the run is bound by
  the demand-driven spawn's spreading, not by the engine step.
* fib(20) 8×8: **18,669 cycles = 15.9× fewer than TACHYON-128** (296,931).
* Regression on v4: units 42/42, programs 268/268, fuzz 600/600 + big 200/200, security 420/420,
  memory pressure 36/36, mutants 39/39 (7 new).
* Python fabric model: the VHU and the v4 costs are modelled (`Cell.vhu_chain`); it remains
  cycle-approximate.

### Benchmarks, v3 engine (step 5; Verilator RTL, cycle accurate, 1024 node + 1024 var slots per cell)

`python3 bench/bench.py --8x8 --progs fib:20,treesum_direct:14,treesum:9 --tag v3` → `results/bench_v3.{json,md}`.

| program | mesh | ok | interactions | cycles | speed-up vs 1x1 | interactions/cycle | cell utilisation | LINK msgs | NODE msgs | SPAWN msgs | msgs/interaction | busiest / idlest cell (interactions) | peak nodes / vars in one cell |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| fib(20) | 1x1 | yes | 295,525 | 1,006,974 | 1.00x | 0.293 | 100% | 0 | 0 | 0 | 0.00 | 295,525 / 295,525 | 69 / 108 |
| fib(20) | 2x2 | yes | 295,525 | 252,422 | 3.99x | 1.171 | 100% | 185 | 57 | 57 | 0.00 | 73,931 / 73,831 | 66 / 102 |
| fib(20) | 4x4 | yes | 295,525 | 67,105 | 15.01x | 4.404 | 95% | 8,935 | 2,453 | 2,453 | 0.05 | 19,558 / 17,141 | 70 / 133 |
| fib(20) | 8x8 | yes | 295,525 | 26,171 | 38.48x | 11.292 | 64% | 38,072 | 10,330 | 10,330 | 0.20 | 7,461 / 2,069 | 65 / 116 |
| treesum_direct(14) | 1x1 | yes | 245,750 | 753,632 | 1.00x | 0.326 | 100% | 0 | 0 | 0 | 0.00 | 245,750 / 245,750 | 32 / 75 |
| treesum_direct(14) | 2x2 | yes | 245,750 | 189,110 | 3.99x | 1.300 | 100% | 642 | 144 | 144 | 0.00 | 61,455 / 61,427 | 35 / 88 |
| treesum_direct(14) | 4x4 | yes | 245,750 | 48,577 | 15.51x | 5.059 | 98% | 6,158 | 1,378 | 1,378 | 0.04 | 15,633 / 15,139 | 48 / 139 |
| treesum_direct(14) | 8x8 | yes | 245,750 | 23,406 | 32.20x | 10.499 | 57% | 67,937 | 15,409 | 15,409 | 0.40 | 7,397 / 754 | 40 / 113 |
| treesum(9) | 1x1* | yes | 18,410 | 71,590 | 1.00x | 0.257 | 100% | 0 | 0 | 0 | 0.00 | 18,410 / 18,410 | 1032 / 1563 |
| treesum(9) | 2x2 | yes | 18,410 | 20,119 | 3.56x | 0.915 | 93% | 1,924 | 715 | 291 | 0.16 | 4,883 / 4,418 | 571 / 872 |
| treesum(9) | 4x4 | yes | 18,410 | 6,299 | 11.37x | 2.923 | 78% | 4,699 | 1,686 | 768 | 0.39 | 1,481 / 974 | 198 / 315 |
| treesum(9) | 8x8 | yes | 18,410 | 2,677 | 26.74x | 6.877 | 51% | 10,121 | 3,505 | 1,699 | 0.83 | 538 / 67 | 73 / 126 |

v3 against v1 (register-file cell, table below): fib(20) on one cell drops from 1,565,188 to 1,006,974 cycles
(**3.41 cycles/interaction**, v1 5.30, v2 8.82); 8×8 from 60,948 to 26,171 cycles (38.5× over one cell,
64% utilisation). treesum(9) 8×8: 6,830 → 2,677 cycles. The scaling columns improve too, because a
shorter step makes cells finish and turn `hungry` sooner.

### Benchmarks, v1 register-file cell (historical, commit 97aa2c0)

| program | mesh | ok | interactions | cycles | speed-up vs 1x1 | interactions/cycle | cell utilisation | LINK msgs | NODE msgs | SPAWN msgs | msgs/interaction | busiest / idlest cell (interactions) | peak nodes / vars in one cell |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| fib(20) | 1x1 | yes | 295,525 | 1,565,188 | 1.00x | 0.189 | 100% | 0 | 0 | 0 | 0.00 | 295,525 / 295,525 | 69 / 108 |
| fib(20) | 2x2 | yes | 295,525 | 392,241 | 3.99x | 0.753 | 100% | 254 | 76 | 76 | 0.00 | 73,958 / 73,806 | 65 / 101 |
| fib(20) | 4x4 | yes | 295,525 | 114,293 | 13.69x | 2.586 | 89% | 21,652 | 5,912 | 5,912 | 0.11 | 21,320 / 14,869 | 64 / 114 |
| fib(20) | 8x8 | yes | 295,525 | 60,948 | 25.68x | 4.849 | 44% | 56,424 | 15,324 | 15,324 | 0.29 | 11,275 / 557 | 65 / 113 |
| treesum_direct(14) | 1x1 | yes | 245,750 | 1,228,750 | 1.00x | 0.200 | 100% | 0 | 0 | 0 | 0.00 | 245,750 / 245,750 | 32 / 75 |
| treesum_direct(14) | 2x2 | yes | 245,750 | 308,061 | 3.99x | 0.798 | 100% | 337 | 85 | 85 | 0.00 | 61,468 / 61,407 | 32 / 75 |
| treesum_direct(14) | 4x4 | yes | 245,750 | 78,479 | 15.66x | 3.131 | 99% | 3,215 | 769 | 769 | 0.02 | 15,588 / 15,166 | 31 / 84 |
| treesum_direct(14) | 8x8 | yes | 245,750 | 32,044 | 38.35x | 7.669 | 66% | 47,366 | 11,092 | 11,092 | 0.28 | 6,272 / 1,123 | 32 / 95 |
| treesum(9) | 1x1* | yes | 18,410 | 120,174 | 1.00x | 0.153 | 100% | 0 | 0 | 0 | 0.00 | 18,410 / 18,410 | 1032 / 1563 |
| treesum(9) | 2x2 | yes | 18,410 | 32,107 | 3.74x | 0.573 | 97% | 1,449 | 547 | 197 | 0.12 | 4,625 / 4,538 | 264 / 413 |
| treesum(9) | 4x4 | yes | 18,410 | 9,058 | 13.27x | 2.032 | 89% | 3,277 | 1,208 | 499 | 0.27 | 1,245 / 1,022 | 152 / 238 |
| treesum(9) | 8x8 | yes | 18,410 | 6,830 | 17.60x | 2.695 | 35% | 11,275 | 3,952 | 2,014 | 0.94 | 911 / 31 | 123 / 188 |
| qsort(40) | 1x1 | yes | 13,855 | 95,149 | 1.00x | 0.146 | 100% | 0 | 0 | 0 | 0.00 | 13,855 / 13,855 | 408 / 745 |
| qsort(40) | 2x2 | yes | 13,855 | 31,259 | 3.04x | 0.443 | 87% | 4,847 | 1,857 | 339 | 0.51 | 3,496 / 3,418 | 228 / 392 |
| qsort(40) | 4x4 | yes | 13,855 | 19,021 | 5.00x | 0.728 | 44% | 13,276 | 4,879 | 1,515 | 1.42 | 982 / 677 | 91 / 134 |
| qsort(40) | 8x8 | yes | 13,855 | 17,083 | 5.57x | 0.811 | 13% | 15,378 | 5,624 | 1,860 | 1.65 | 396 / 52 | 45 / 72 |
| list(120) | 1x1* | yes | 6,269 | 42,760 | 1.00x | 0.147 | 100% | 0 | 0 | 0 | 0.00 | 6,269 / 6,269 | 966 / 1691 |
| list(120) | 2x2 | yes | 6,269 | 18,486 | 2.31x | 0.339 | 74% | 4,181 | 1,538 | 401 | 0.98 | 1,601 / 1,532 | 108 / 159 |
| list(120) | 4x4 | yes | 6,269 | 15,171 | 2.82x | 0.413 | 26% | 7,105 | 2,561 | 876 | 1.68 | 477 / 230 | 48 / 76 |
| list(120) | 8x8 | yes | 6,269 | 14,306 | 2.99x | 0.438 | 7% | 7,427 | 2,671 | 940 | 1.76 | 234 / 35 | 26 / 37 |
| sum(1000) | 1x1 | yes | 13,008 | 65,041 | 1.00x | 0.200 | 100% | 0 | 0 | 0 | 0.00 | 13,008 / 13,008 | 1007 / 1009 |
| sum(1000) | 2x2 | yes | 13,008 | 63,170 | 1.03x | 0.206 | 35% | 8,001 | 3,001 | 2,001 | 1.00 | 4,006 / 2,500 | 503 / 504 |
| sum(1000) | 4x4 | yes | 13,008 | 64,089 | 1.01x | 0.203 | 9% | 8,359 | 3,001 | 2,001 | 1.03 | 1,184 / 500 | 144 / 144 |
| sum(1000) | 8x8 | yes | 13,008 | 64,319 | 1.01x | 0.202 | 2% | 8,451 | 3,001 | 2,001 | 1.03 | 312 / 115 | 41 / 41 |
| fact(12) | 1x1 | yes | 164 | 821 | 1.00x | 0.200 | 100% | 0 | 0 | 0 | 0.00 | 164 / 164 | 19 / 21 |
| fact(12) | 2x2 | yes | 164 | 798 | 1.03x | 0.206 | 35% | 97 | 37 | 25 | 0.97 | 54 / 27 | 10 / 11 |
| fact(12) | 4x4 | yes | 164 | 824 | 1.00x | 0.199 | 9% | 105 | 37 | 25 | 1.02 | 30 / 0 | 7 / 7 |
| fact(12) | 8x8 | yes | 164 | 824 | 1.00x | 0.199 | 2% | 105 | 37 | 25 | 1.02 | 30 / 0 | 7 / 7 |

`*` = the program does not fit in one 1024-slot cell (a 512-leaf tree or a 120-element Scott list
needs > 1024 vars). The sequential baseline is therefore a single cell with 4096 slots. Speed-up is
cycles(1 cell) / cycles(W×H).

Observations:
* **Parallel recursion scales.**

  | program | 2×2 (4 cells) | 4×4 (16 cells) | 8×8 (64 cells) |
  |---|---:|---:|---:|
  | direct tree sum (2¹⁴ leaves) | 3.99× | 15.7× (99% utilisation) | 38× |
  | fib(20) | 3.99× | 13.7× | 25.7× |
  | tree build + sum (2⁹ leaves) | 3.7× | 13.3× | 17.6× |

  At 8×8 the parallel work no longer fills the mesh: utilisation is 35–66%, and the cells far from
  cell (0,0) get work late.
* **Sequential programs do not scale, and should not.**
  * sum(1000) and fact(12) are a single dependency chain: ≈1.0× on every mesh.
  * qsort(40) reaches 5×, limited by the sequential partition passes and append.
  * list map + sum reaches 3×, from producer/consumer pipelining.
* **Message traffic is low.** For the parallel programs it stays at 0.00–0.27 messages per
  interaction up to 4×4. Demand-driven spawning keeps work local until a neighbour is hungry. The
  earlier round-robin push policy needed ≈0.5 and could exhaust a 2×2 fabric's memory.
* **Cost per interaction.** One cell does 1 interaction per 5–6.5 cycles (IDLE pick + LINK + pushes +
  var links). The var `link` is the dominant cost, at ≈1.5–2.5 per interaction.

### SRAM-style cell and synthesis (step 2)

The cell's storage is now written as **1R1W synchronous SRAMs** (one write statement and one registered
read per array): node RAM 1024×132 b (`{owner, aux2, aux1}`), var RAM 1024×68 b (`{owner, port}`),
the free-node / free-var stacks and the task stack as a small register cache over a 1R1W SRAM, and
the definition ROM / directory as 1R ROMs with a loader write port. The owner tags moved into the
RAM words. The same RTL is simulated by Verilator and synthesised by Yosys' native front end (no
`sv2v`/slang; the RTL uses the SystemVerilog subset both accept: shared `omega_defs.svh`, functions
included per module).

Yosys 0.70 (yowasp, WebAssembly), generic gates after `techmap; abc`, memories kept as `$mem_v2`
macros (`synth/synth_cell.ys`, reports in `results/synth/`, GE = NAND2 equivalents from
`synth/ge.py`, same weights for both designs):

| design | generic cells | flip-flops | GE (logic) | SRAM / ROM macros |
|---|---:|---:|---:|---|
| Ω cell v2, 1024 slots (router 1,612 cells) | 92,420 | 4,240 | 147,102 | 7 macros, 886,784 bits (node 135 Kb, var 70 Kb, task stack 133 Kb, free stacks 20 Kb, ROM 524 Kb, dir 4 Kb) |
| Ω cell v2, 256 slots | 54,403 | 3,152 | 92,741 | 7 macros |
| **Ω cell v3 + step 4, 1024 slots** (router 1,612 cells; `results/synth/stat_v3_cell_1024.txt`) | **155,725** | 4,271 | **233,164** | 8 macros, 1,177,600 bits (v2 + redex ROM 2048×128 b and a 128-bit directory word) |
| TACHYON-128 core v4 (`cpu128/results/synth_stat_abc.txt`) | 129,811 | 8,519 | 217,636 | 3 macros (register file ≈ 26 Kbit) |

v3 costs +59% logic over v2 (read-ahead address muxes with write bypass, 4-wide allocation, the
write queue, the PULL / roomy logic). It is about 1.07× one TACHYON-128 core in logic GE.

Cost of the SRAM discipline: fib(20) on one cell takes 2,605,000 cycles, **8.82 cycles/interaction**
(v1 register-file cell: 5.30), because every var exchange and node read now waits one cycle for the
synchronous read. Step 3 below removes that with read-ahead addressing.

### v3 engine: one link step per cycle (step 3)

Every read address is computed one cycle ahead from the engine's *next* state (look-ahead), with a
write bypass, so a link step finds its var / node data already read from the synchronous RAMs. The
rule, its node writes and the first resulting link share one cycle; the extra node writes of a
commutation drain in `S_WQ` (the last one bypassed into the read-ahead); the free stacks and task
stack are register caches over 1R1W SRAMs (refill/spill one entry per cycle); EXPAND allocates up to
4 node + 4 var slots per cycle and then writes node *i*, var tag *i* and redex *i* in the same cycle.
The IDLE cycle is gone: a finishing step picks the next task or message in the same cycle.
Full regression on v3: units 35/35, programs 268/268, fuzz 600/600 + big 200/200, security 420/420,
mutants 27/27 (5 new v3 mutants). Cycle numbers: see the benchmark section (step 5).

### Memory pressure (step 4)

Each cell drives a `roomy` wire (free node and var slots ≥ SLOTS/4, cleared below SLOTS/8);
`hungry` requires `roomy`. Out of slots, a cell moves work from poor to rich instead of retrying in
place: SPAWNs go to a roomy neighbour, a SWI node goes as `NODE` to a roomy neighbour, and a
commutation uses the new `PULL` message (the roomy neighbour re-homes P, then asks Q's cell for Q,
which migrates with the ordinary NODE rule; SPEC §4, §5). `tests/test_mempress.py` (36 cases): cell
(0,0) pre-filled with foreign ballast so that only 4–30 slots are free there (30 cases; the v3 RTL
without step 4 livelocks on 7 of them), capacity cases with small cells, and the security fuzz case
265. Regression: units 35/35, programs 268/268, fuzz 600/600 + 200/200, security 420/420,
memory pressure 36/36, mutants 29/29 (2 new: roomy neighbours ignored; hungry without roomy).

### Cluster definition ROM (step 7)

The node-template and redex-template ROMs (786 Kbit, 67% of a v3 cell's 1.18 Mbit) were replicated in
every cell. Now one `omega_rom` serves a **cluster** of CW×CH cells (`omega_mesh` parameters `CW`,
`CH`, `RPORTS`; `OMEGA_CLUSTER=2x2:1` is the default in the harness and the regression). SPEC §5.3 has
the protocol:

* **One ROM word = two template entries.** The loader aligns definitions to even entries, so an
  EXPAND, which writes one entry per cycle, needs a grant only every other cycle. The cell keeps the
  last word it received (512 flip-flops) and uses an arriving word directly.
* **Request / grant.** Requests are combinational from registers. A round-robin arbiter grants up to
  `RPORTS` cells per cycle, and the data comes back one cycle later. In `S_LINK` the request is
  speculative: when the link may start an expansion here, the cell asks for word 0 of the definition
  whose directory word was read ahead. A missed grant only holds `S_EXN`.
* The per-cell directory (256×128 b) stays local: it is read ahead on every link step.

Trade-offs measured on the RTL. First, fib(15) on the earlier one-entry-per-word variant, which shows
why words hold pairs:

| organisation | ROM storage per cell | fib(15) 2×2 | fib(15) 4×4 |
|---|---:|---:|---:|
| replicated (v3) | 786 Kbit | 23,784 | 6,881 |
| 2×2 cluster, 1 port, 1 entry/word | 197 Kbit | 32,182 (+35%) | 8,893 (+29%) |
| 2×2 cluster, 2 ports, 1 entry/word | 197 Kbit, 2R ROM | 24,403 (+3%) | 7,195 (+5%) |
| **2×2 cluster, 1 port, 2 entries/word** | **197 Kbit** | **24,118 (+1.4%)** | **7,174 (+4%)** |
| 4×4 cluster, 1 port, 2 entries/word | 49 Kbit | — | 12,444 (+81%) |

Then the step-5 benchmark set, 1×1 to 8×8, per configuration (`bench/bench.py --cluster CWxCH:P`,
`results/bench_c*.json`; the 1×1 row is identical in all configurations because one cell never
contends):

| program | mesh | replicated (1x1) | 2x2, 1 port | 2x2, 2 ports | 4x4, 1 port | 4x4, 2 ports |
|---|---|---:|---:|---:|---:|---:|
| fib(20) | 1x1 | 1,006,974 | 1,006,974 (+0.0%) | 1,006,974 (+0.0%) | 1,006,974 (+0.0%) | 1,006,974 (+0.0%) |
| fib(20) | 2x2 | 252,422 | 269,881 (+6.9%) | 253,898 (+0.6%) | 269,881 (+6.9%) | 253,898 (+0.6%) |
| fib(20) | 4x4 | 67,105 | 70,938 (+5.7%) | 66,286 (-1.2%) | 133,348 (+98.7%) | 75,800 (+13.0%) |
| fib(20) | 8x8 | 26,171 | 25,635 (-2.0%) | — | — | — |
| treesum_direct(14) | 1x1 | 753,632 | 753,632 (+0.0%) | 753,632 (+0.0%) | 753,632 (+0.0%) | 753,632 (+0.0%) |
| treesum_direct(14) | 2x2 | 189,110 | 211,721 (+12.0%) | 189,286 (+0.1%) | 211,721 (+12.0%) | 189,286 (+0.1%) |
| treesum_direct(14) | 4x4 | 48,577 | 53,077 (+9.3%) | 48,423 (-0.3%) | 115,594 (+138.0%) | 61,952 (+27.5%) |
| treesum_direct(14) | 8x8 | 23,406 | 19,492 (-16.7%) | — | — | — |
| treesum(9) | 1x1 | 71,590 | 71,590 (+0.0%) | 71,590 (+0.0%) | 71,590 (+0.0%) | 71,590 (+0.0%) |
| treesum(9) | 2x2 | 20,119 | 19,306 (-4.0%) | 19,954 (-0.8%) | 19,306 (-4.0%) | 19,954 (-0.8%) |
| treesum(9) | 4x4 | 6,299 | 6,245 (-0.9%) | 5,594 (-11.2%) | 10,972 (+74.2%) | 7,400 (+17.5%) |
| treesum(9) | 8x8 | 2,677 | 3,195 (+19.4%) | — | — | — |

* **Default: 2×2 cells per ROM, one port.** ROM storage per cell drops 4× (786 → 197 Kbit; the whole
  cell from 1.18 Mbit to ≈0.59 Mbit). It costs 6–12% cycles on 2×2 and 4×4 meshes for the
  expansion-heavy programs. At 8×8, where the mesh is not saturated, the difference is schedule noise
  (−17% to +19%): the demand-driven spawn reacts to small timing changes.
* A second port removes the contention (≤ 1% except schedule noise) at the cost of a 2-read-port
  ROM. A 4×4 cluster needs at least two ports: with one it is bandwidth-bound (+74% to +138% on 4×4),
  because fib and the tree sums expand a definition every ≈9 interactions.
* Correctness does not depend on the arbitration (a missed grant only delays an EXPAND).
  Regression on the default configuration: units 42/42, programs 268/268, fuzz 600/600 + big
  200/200, security 420/420, memory pressure 36/36, mutants 32/32 (3 new).

### Comparison with TACHYON-128 (same algorithm: naive recursive fib(20))

| machine | work | cycles | vs TACHYON-128 |
|---|---|---:|---:|
| TACHYON-128 v6 (5-stage pipeline, BTB+RAS, tcc128 `-O`; `cpu128/README.md`, cc bench `fib`, includes `printf`) | 274,303 instructions, CPI 1.08 | **296,931** | 1.00 |
| TACHYON-Ω v3, 1×1 | 295,525 interactions, 3.41 cycles each | 1,006,974 | 3.39× slower |
| TACHYON-Ω v3, 2×2 | | 252,422 | 1.18× faster |
| TACHYON-Ω v3, 4×4 | | 67,105 | **4.42× faster** |
| TACHYON-Ω v3, 8×8 | | 26,171 | **11.35× faster** |

#### Area-normalised (logic GE × cycles, lower is better)

Area × time for one fib(20), counting **logic only** (NAND2-equivalent GE from the same Yosys flow and
the same `synth/ge.py` weights for both designs; SRAM/ROM excluded on both sides):

| machine | cells | logic GE | fib(20) cycles | GE × cycles | vs TACHYON-128 |
|---|---:|---:|---:|---:|---:|
| TACHYON-128 (GE: v4 core synthesis `cpu128/results/synth_stat_abc.txt`; cycles: v6) | 1 | 217,636 | 296,931 | 6.46 × 10¹⁰ | 1.00 |
| TACHYON-Ω v3, 1×1 | 1 | 233,164 | 1,006,974 | 2.35 × 10¹¹ | 3.63× worse |
| TACHYON-Ω v3, 2×2 | 4 | 932,656 | 252,422 | 2.35 × 10¹¹ | 3.64× worse |
| TACHYON-Ω v3, 4×4 | 16 | 3,730,624 | 67,105 | 2.50 × 10¹¹ | 3.87× worse |
| TACHYON-Ω v3, 8×8 | 64 | 14,922,496 | 26,171 | 3.91 × 10¹¹ | 6.04× worse |

What this comparison does and does not say:
* **Per unit of logic, Ω v3 is ≈3.6× less efficient than a pipelined von Neumann core** on this
  program, and that ratio holds almost flat up to 4×4 (near-linear speed-up). At 8×8 the mesh is only
  64% utilised, so area × time grows to 6×. The fabric buys *latency* (11× fewer cycles at 8×8) with
  area, and the parallelism is found automatically: the same source runs on any mesh with no threads,
  locks or scheduling code.
* **Memory is not in the table, and it favours the CPU here.** Each Ω cell carries 1.18 Mbit of SRAM/ROM
  (node, var, task stack, free stacks, definition ROMs; the ROMs are replicated per cell); the CPU's
  register file is ≈26 Kbit, but a real CPU also needs caches and DRAM, which the fabric does not.
  Shrinking the per-cell ROM (shared ROM per cluster) is the largest available area win.
* **GE is technology-independent** (generic gates, no library, no timing). Clock frequency and energy
  are not compared; the Ω cell's critical path (read-ahead address → SRAM) is unmeasured.
* **The numbers are 32-bit.** TACHYON-128 computes with 128-bit registers. Ω's NUM atoms are 32-bit.

### Standard-cell area and Fmax (step 8: Nangate45, pre-layout)

> **Not re-synthesised for v4 (step 9).** The area and Fmax numbers below are from commit `03c8f9f`
> (v3 engine + cluster ROM). The v4 engine adds a second write port to the node and var RAMs (2W macros,
> roughly +50% macro area each in this model), a 512-bit ROM word buffer and the var-hop unit, so the
> v4 cell is larger; area × time tables below still use the step-8 cycle counts.

`synth/flow.py` maps the Ω cell, the cluster ROM and the TACHYON-128 core (`cpu128/rtl/tx_core.sv`,
read-only) onto the **Nangate45 (FreePDK45) Open Cell Library**, typical corner, with one flow:
Yosys 0.70 (`dfflibmap` + `abc -D 2000`), every memory kept as a black-box macro whose area is
bits × the mean density of the OpenROAD **fakeram45** macros (0.533 µm²/bit, +50% per extra port), a
fanout repair pass (`synth/buffer_nets.py`, buffer trees above 16 sinks, buffers counted in the area)
and **OpenSTA** pre-layout timing with the library's wire-load model. Place and route is out of scope
(see the scope statement at the top), so these are rough pre-layout estimates for internal reference only.
Reports: `synth/out/<design>/{stat.txt, sta.txt, summary.json}`; table: `bench/area_table.py` →
`results/area_fmax.md`.

| design | std-cell area µm² (of which fanout buffers) | memory µm² (bits) | total µm² | Fmax MHz (critical path) |
|---|---:|---:|---:|---:|
| `omega_cell` (1024 node + 1024 var slots, router included) | 150,915 (14,847) | 348,558 (391,168) | 499,473 | **35.0** (engine next state → read-ahead node RAM address, ≈28.5 ns) |
| `omega_rom` (one per 2×2 cluster, 1 port) | 2,501 (369) | 628,386 (786,432) | 630,887 | 1,304 |
| per Ω cell with ¼ ROM | 151,540 | 505,654 | **657,195** | 35.0 |
| TACHYON-128 `tx_core` (v6 RTL) | 166,993 (8,010) | 28,450 (26,976) | **195,443** | **95.5** (operand forwarding → mul/div unit, ≈10.4 ns) |

fib(20), area including every cell and every cluster ROM the mesh needs (cycles from
`results/bench_c2x2p1.json`; TACHYON-128 cycles from its v6 benchmark):

| machine | cells + ROMs | area mm² (std cell / memory) | per cell mm² | Fmax MHz | fib(20) cycles | time µs | area × cycles (vs T-128) | std-cell area × cycles (vs T-128) | area × time (vs T-128) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| TACHYON-128 tx_core (v6 cycles) | 1 + 0 | 0.195 (0.167 / 0.028) | 0.195 | 95.5 | 296,931 | 3,110 (1.00×) | 1.00× | 1.00× | 1.00× |
| TACHYON-Omega 1x1 | 1 + 1 | 1.130 (0.153 / 0.977) | 1.130 | 35.0 | 1,006,974 | 28,783 (9.25×) | 19.61× | 3.12× | 53.52× |
| TACHYON-Omega 2x2 | 4 + 1 | 2.629 (0.606 / 2.023) | 0.657 | 35.0 | 269,881 | 7,714 (2.48×) | 12.23× | 3.30× | 33.36× |
| TACHYON-Omega 4x4 | 16 + 4 | 10.515 (2.425 / 8.090) | 0.657 | 35.0 | 70,938 | 2,028 (0.65×) | 12.85× | 3.47× | 35.07× |
| TACHYON-Omega 8x8 | 64 + 16 | 42.060 (9.699 / 32.362) | 0.657 | 35.0 | 25,635 | 733 (0.24×) | 18.58× | 5.01× | 50.70× |

What this says:
* **The Ω cell runs at about a third of TACHYON-128's clock.** The v3 engine does a whole link step per
  cycle *and* computes the next step's RAM read-ahead address from the next-state logic in the same
  cycle (one `always_ff` block with blocking temporaries: task-stack push/pop, free-stack pops, the
  next link, then the address). That chain is ≈28.5 ns pre-layout. TACHYON-128's 5-stage pipeline
  is limited by its mul/div operand path at ≈10.4 ns. Splitting the read-ahead into its own pipeline
  stage (one more cycle per dependent step, or a predicted address) is the obvious timing fix and would
  raise cycles per interaction; it is not done.
* **Wall-clock: Ω only wins from 4×4 up** (4×4: 0.65× the time, 8×8: 0.24×, i.e. 4.2× faster), against
  2.5× slower at 2×2 and 9.3× slower on one cell.
* **Area × cycles is 12–20× worse, area × time 33–54× worse.** Memory dominates: a cell carries
  0.506 mm² of SRAM/ROM (node RAM 0.144, task queue 0.106, var RAM 0.056, directory 0.026, ¼ ROM
  0.157) against 0.152 mm² of logic. Counting standard cells only, Ω is 3.1–5.0× worse in area ×
  cycles, consistent with the generic-gate GE estimate of step 5 (3.6–6.0×).
* The comparison omits what TACHYON-128 needs and Ω does not (caches, DRAM interface), and Ω's 1024
  slots per cell are sized for the test suite, not tuned; smaller node RAM / task queue is the next
  area lever.

## Known gaps

1. **Owner capabilities: scope.** 15 tenants (4-bit owner, 15 = free). A trapped tenant is not
   killed or cleaned up: its offending operation is dropped and the rest of its graph may stay in
   memory (no reclamation of a misbehaving tenant's slots). There is no timing isolation: tenants
   share cells, routers and memory capacity, so one tenant can slow another or exhaust shared memory.
   The ROM is shared, so tenants see each other's definitions (they cannot forge an owner, but code is
   not confidential). Forged pointers to slots the attacker itself owns are not trapped (no isolation
   issue, but the attacker can corrupt its own graph).
2. **Area and Fmax are rough pre-layout estimates.** Physical design (OpenROAD, place and route, timing
   closure) is out of scope permanently (scope statement at the top), so `synth/flow.py` stops after
   synthesis + OpenSTA: no floorplan, placement, clock tree or routing, wire delay from the Nangate45
   wire-load model only (real routed timing on a 0.66 mm² cell will be worse), the fanout repair is a
   simple buffer-tree pass instead of `repair_design`/resizing, and `abc` maps for delay without
   retiming or gate sizing. Memory macros are *not* generated: their area is bits × the average
   fakeram45 density (+50% per extra port) and their timing is the fakeram45 clock-to-out/setup, so
   the memory area is good to perhaps ±30%. Yosys maps logic only for the typical corner. Both
   designs go through the same flow, so the *ratio* is more trustworthy than the absolute numbers.
   The per-slot `nalloc` valid bits are flip-flops (1 per node slot).
3. **Out-of-memory handling: local recovery only.** Step 4 moves work from poor to rich cells
   (`roomy` wire, SPAWN/NODE/PULL to roomy neighbours), but:
   * task-stack overflow (`err = 1`) or a 1×1 cell that cannot place an expansion (`err = 2`) still
     halts the cell;
   * a *globally* full fabric still bounces work (status 3 / "no progress"); there is no spilling to
     off-fabric memory and spawning is not throttled. Step 10's retry slot parks a retry for `rto`
     cycles (8 since step 19, 32 before) and escalates after 4 parks; since step 19 a homeless SPAWN and
     escalated retries follow the room-distance gradient downhill, but only within `rgrad` = 3 hops of a
     roomy cell: room farther away is still found by round-robin diffusion. SPEC §7.1 (step 20) argues
     network deadlock freedom and placement liveness within the gradient, and shows that **completion
     cannot be guaranteed by any local mechanism**: treesum(9) 3×3 with 264 free slots in total (2.3× the
     115 a single cell needs depth first) stops on 20 / 20 seeds, because the parallel order fills and
     fragments the memory until no pending SPAWN fits anywhere. Only one retry fits the slot, further ones
     take the old path. The default costs treesum(6) 3×3 under global pressure 3.7% cycles against
     `+rto=32` (RTL, 13 seeds; step 20 traced it to the room cell doing all the work, and getting it back
     needs step 18's spreading, which livelocks treesum(9)); step 20's reserve 1 narrows list(20) 3×2 /
     fib(12) 6×6 to +3% / +6% against `+rto=8` alone (which livelocks); the full-cell pass-on (rule 4)
     moves a blocked `NODE` / `PULL` on but has no hop budget, so on a globally full fabric it can bounce
     like the SPAWNs (status 3, as before);
   * mutant 27 (roomy offload disabled) survives on its own since step 10: escalation alone rescues
     every pressure case in the suite, so the roomy offload is now only a fast path, and no current
     benchmark shows its speed benefit.
4. **Limits on sizes.**
   * One definition may have at most 255 nodes, 255 vars and 255 redexes (8-bit counts), and the ROM
     holds 4096 entries.
   * There are at most 16×16 cells and 4096 slots per cell.
   * NUM atoms are u32 only (no signed or float types).
5. **Termination detection** is a combinational AND tree over all cells, fine for simulation. A large
   chip needs a pipelined tree or a token ring (SPEC §8).
6. **Python fabric model is cycle-approximate**, not lockstep with the RTL. It charges per-task costs.
   Both are checked against the semantic model, not against each other cycle by cycle.
7. **Frontend.**
   * The type checker is shape-only: data types are not parameterised and constructor fields are
     untyped (a list may mix numbers and functions); mutual recursion is monomorphic.
   * DUP labels are allocated one per binder. Programs that duplicate closures that themselves
     duplicate can hit the usual interaction-combinator oracle problem; no such program is in the
     suite.
   * Arm lifting applies to `switch` and `match` only. Pattern matching compiles to nested Scott
     matches, so a deep pattern costs one match (and possibly one lifted definition) per level.
   * Results that are lazy references at the root (e.g. `def main = Nil`) read back as `@Nil`.
8. **Mesh flits are 266 bits wide** (one NODE message carries a whole 128-bit node plus two ports). A
   narrower physical link would serialise them into several flits.
9. **No optimal (Lamping/Δ-Nets) reduction.** Sharing is plain interaction-combinator duplication.

10. **CI covers the quick subset only**, on Ubuntu 24.04's Verilator 5.020 (units, programs without
    random cases, 80 RTL fuzz cases, 20 multi-tenant cases, memory-pressure quick set). The full
    regression (fuzz 600 + big 200, security 420, mutants) runs locally on Verilator 5.052.

11. **Spawn policy (steps 11–13) is heuristic.** The producer / strict split is a static call-graph
    property: a strict recursion that would profit from spreading, or a producer whose consumer is
    sequential anyway, is classified wrongly, and higher-order code (a fold whose operator is a
    closure) is classed strict. The adaptive part is a per-cell message budget, not a per-definition
    measurement: per-definition granularity counters were tried and rejected (README step 13). The
    governor reacts after 32 interactions, so very short programs run at the reset level. treesum(9)
    on 8×8 still varies with the arbitration seed (step 13: 2,017–2,792 over seeds 1–8; step 14: 1,984–2,506; step 15: 1,914–2,435), list(120) on 2×2 is 0.7% slower
    than step 12 (within seed noise), and every policy number is for programs of this suite only.
    Going from 4×4 to 8×8 does not help the low-parallel programs: sort(20) 5,910 → 6,004 (+1.6%) and
    higher(100) 7,605 → 7,780 (+2.3%) cycles, higher's msgs/interaction 0.320 → 0.347 (mean of 4 seeds);
    both stay faster than 1×1 (2.17× / 1.58×) and below 0.5 msgs/interaction.

12. **Step 14 fork deque: partial, and the governor half is off.** The fork deque is on by default only
    for fork definitions that are not stream-fed (directory bit 59), because with every fork definition
    (the fabric study's s14c) qsort(40) gets 5–7% slower; the bit is a static call-graph property, like the
    producer hint. The governor relax nb5l1 from the same study regresses list(120) and higher(100) on the
    RTL by up to 9.8% (and pushes higher(100) 4×4 to 0.52 msgs/interaction), and the milder k = 3 gains
    nothing, so it ships as a knob (`+govnb`, `+govl0`), default off. The RTL does not reproduce the
    fabric model's variance result in full: treesum(9) 8×8 sd −23% (fabric −59%), fib(20) 8×8 sd +34%
    (though every seed is faster than the step-13 mean). treesum(9) 8×8's rise from 0.43 to 0.53
    msgs/interaction is fixed in step 15 (0.466: data-walking forks stay off the deque); its remaining +8% over
    step 13 comes from `gen` gives, whose subtrees the walk partly follows. The low-parallel programs (qsort, list, sort, higher, sum) gain nothing from step
    14. The area figure is an estimate (≈ 8% of the cell's standard-cell part, not synthesised).

## Next steps (suggested)

1. Microarchitecture: shorten the read-ahead address chain in RTL (a pipelining / architecture question;
   place and route, routed area and timing closure are out of scope). Shrink the node RAM / task queue.
2. Re-synthesise the v4 cell (2W RAMs, VHU) and re-do the area × time comparison. Cut cycles per
   interaction below 2.36: dual-issue independent tasks, or overlap the rule cycle with the next pick.
3. Global memory pressure: a completion guarantee needs memory-aware admission, not re-routing (SPEC §7.1,
   step 20 counterexample): e.g. a global low-memory signal (an OR tree like the quiescence tree) that makes
   every cell stop giving work away and reduce depth first, bounding the peak by the sequential one, or
   spilling to off-fabric memory. The treesum(6) 3×3 +3.7% needs a signal that tells "the room is far from
   full" from "the room will run out" (the same spreading helps one and livelocks the other); a relative
   `roomy` watermark (free ≥ largest definition + `rsv` instead of SLOTS/4) would let the gradient see room
   that is spread thin. Throttle SPAWN bouncing on a globally full fabric.
4. Bigger language: signed numbers, strings, `fold`/`bend`, parameterised data types; a TACHYON-128 host
   interface (DMA of graph images, result readback).
5. Fork deque: narrower entries (`{REF label, owner, x}`, 76 b) and one hint vector; a dynamic locality
   test (give a data-walking task when its argument has already left the cell) instead of step 15's static
   bit (step 16 probe: tried at push and at give time on the fabric model, worse than the static bit, because the walked
   structure has not arrived when the task is pushed); a governor signal that
   separates "neighbour idle because the program is sequential" from "neighbour starving", so the relax
   helps qsort without hurting list / higher.
6. Spawn policy: shipping the partner node with a SPAWN (step 16 probe) helps treesum / sort and hurts
   qsort / list / fib on the fabric model; a selector for it would need a dynamic signal (e.g. whether the
   return wire's consumer is busy), and a per-definition benefit signal measured at the *sender*
   (time until the given work's result returns) to replace the static producer hint.

## Commits

* `9322771` stage 0: port encoding, text IR, semantic reducer
* `6d68b69` stage 1: cycle-level fabric model (cells, mesh routers, LINK/NODE/SPAWN protocol, retry back-pressure, loader image)
* `cb05aa5` stage 2: Omega-lang frontend (lambda + numbers + recursion + Scott data, arm lifting) and program suite
* `fc3d68d` stage 3+4: SystemVerilog RTL (active memory cell, 5-port mesh router, W x H mesh), Verilator TB, Python harness; programs pass on 1x1/2x2/4x4
* `2a4c82c` stage 5a: random net generator, RTL differential fuzz (600/600), directed unit tests (35/35 incl. RTL), mutation knobs + harness
* `759fc50` stage 5b: mutation testing 16/16 caught, SPEC.md, program tests, bench script
* `7be478c` frontend: only lift arms that can reduce (value arms inline) - fixes unexpanded REF results at N=0; program tests 268/268
* `18e4ce5` demand-driven spawn (hungry side-band wires between neighbours) replaces round-robin push: 100x fewer messages, no OOM livelock; per-cell peak occupancy counters; run_all.sh
* `9cccae8` full regression on demand-driven spawn RTL: units 35/35, programs 268/268, fuzz 600/600 + big 200/200, mutants 16/16; README draft
* `97aa2c0` benchmarks (1x1..8x8) with demand-driven spawn; README results, comparison with TACHYON-128, known gaps
* `e5d714a` CI: GitHub Actions quick regression (Verilator units, programs, 80 RTL fuzz cases)
* `7f81d51` owner-capability isolation: per-slot owner tags, CROSS/FORGED/OOB traps in all three models; security suite 420/420
* `10c5346` CI: absolute source paths for Verilator 5.020
* `9ed3ba7` step 2: SRAM-style cell (1R1W synchronous RAMs), Yosys synthesis of one cell
* `c37a922` step 3: v3 engine, one link step per cycle (read-ahead addressing, write bypass)
* `304f5a8` step 4: memory pressure (roomy wire, OOM work moves to roomy neighbours, PULL)
* `74bbbd7` fix: explicit FIFO write-index wrap (Verilator 5.020 CI failure); unbuffered CI output
* `9a19a33` step 5: v3 benchmarks, v3 cell synthesis (233,164 GE), area-normalised comparison
* `1dfad55` step 6: nested / literal / default patterns, Hindley–Milner type checker
* `97b3bec` step 7: cluster definition ROM (`rtl/omega_rom.sv`, 2×2 cells per ROM, pair words, round-robin arbiter), benchmarks per configuration
* `03c8f9f` step 8: standard-cell flow (Yosys → Nangate45, fakeram45 macros, OpenSTA pre-layout), area / Fmax table
* `012c4ff` step 9: v4 engine (wide EXPAND, commutation 2 + 3, var-hop unit, free-var cache overflow fix); fib(20) 1×1 2.36 cycles/interaction; mutants 39/39
* `46e4a1a` step 10: single non-LIFO retry slot with timeout + escalation, no blind round-robin SPAWN, global memory-pressure tests; mempress 43/43, mutants 42/42
* `7642829` step 10 benchmarks incl. 8×8 (fib(20) 8×8 18,669; treesum_direct(14) 8×8 16,914); `OMEGA_SPLIT` for low-memory 8×8 builds
* `25e94a9` README: scope statement (architecture and RTL only; tape-out / physical design permanently out of scope)
* `b75256a` step 11+12: sender-side spawn threshold + fork/rec definition hints (`spawn_k` = 16, `spawn_k2` = 4), local-first var ~ var link orientation; 8×8 msgs/interaction qsort 0.385, list 0.404, sum 0.022; fib(20) 8×8 17,736, treesum_direct(14) 8×8 13,983; units 42/42, programs 279/279, fuzz 600/600 + big 200/200, security 420/420, mempress 43/43, mutants 45/45
* `bd6b226` step 13: producer-recursion hint + per-cell message-budget governor (`gov_b` = 30); qsort(40) 8×8 10,742 cycles (mean of 4 seeds), 0.403 msgs/interaction; fib/treesum unchanged; units 42/42, programs 306/306, fuzz 600/600 + big 200/200, security 420/420, mempress 43/43, mutants 47/47
* `ac2acd5` step 13 gap: 8×8 sum / sort / higher / fact at the default governor
* step 14: per-cell 4-entry fork deque + oldest-fork give (default: fork definitions that are not stream-fed, directory bit 59; `+s14=0` = step 13), governor relax knobs `+govnb` / `+govl0` (default off); 8 seeds: fib(20) 8×8 −10.7%, treesum_direct(14) 8×8 −15.8% (range −53%), treesum(9) 4×4 / 8×8 −6.4% / −5.8%, every other program cycle for cycle as step 13; units 42/42, programs 306/306, step-14 cross-check 90/90, fabric knobs 324/324, fuzz 600/600 + big 200/200, security 420/420, mempress 43/43, mutants 49/49
* step 15: directory bit 59 (fork deque) leaves out data-walking fork recursions (loader only, no RTL change; `OMEGA_DQF_DATA=1` = step 14); 8 seeds: treesum(9) 8×8 2,255 → 2,126 cycles (−5.7%), 0.526 → 0.466 msgs/interaction; every other program cycle for cycle as step 14; units 42/42, programs 315/315, step-14 cross-check 90/90, fabric knobs 1,782/1,782, fuzz 600/600 + big 200/200, security 420/420, mempress 43/43, mutants 49/49
* step 16: two fabric-model probes rejected (dynamic fork-deque locality test; SPAWN carrying the partner node), README section and `results/s16/`; no model / RTL change
* step 17: room-distance gradient for global memory pressure, fabric probe rejected (fewer messages, up to +15% cycles, livelock without parking); README section, `results/s16/`
* step 18: retry-slot timeout as a run-time input (`+rto`, `OMEGA_RTO`; default 32, unchanged): `+rto=8` cuts global-pressure cases by 0.4–58% on RTL but raises the fabric model's livelock rate, so it stays a knob
* step 19: room-distance gradient (`+rgrad`, `OMEGA_RGRAD`) + slot reserve + full-cell pass-on (rule d) fix the short-timeout livelock / deadlock; new defaults `+rto=8 +rgrad=3` (`+rto=32 +rgrad=0` = step 18 cycle for cycle); no stopped run of the new default on either model, global treesum(7) 8×8 28,003 → 7,685 cycles (−72.6%, 30 seeds); units 42/42, programs 315/315, step-14 cross-check 90/90, fuzz 600/600 + big 200/200, security 420/420, mempress 44/44, mutants 51/51
* step 20: slot reserve 4 → 1 as run-time input `+rsv` / `OMEGA_RSV` (`+rsv=4` = step 19): RTL global pressure list(20) 3×2 −3.8%, fib(12) 6×6 −1.6%, treesum(7) 8×8 −1.8%, no stopped run; treesum(6) 3×3 +3.7% vs step 18 traced and kept as a known gap; SPEC §7.1 progress argument with a counterexample (no local mechanism can guarantee completion); fabric probe knobs; units 42/42, programs 315/315, step-14 cross-check 90/90, fuzz 600/600 + big 200/200, security 420/420, mempress 44/44, mutants 52/52, identity 128/128
