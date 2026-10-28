# TACHYON-Ω — a Spatial Interaction-Net Fabric

A processor prototype with **no CPU, no separate memory, no program counter, no shared address space
and no instruction stream**. A program is a graph (an interaction net). The machine is a W×H mesh of
*active memory cells*. Each cell stores part of the graph and rewrites, right where it is stored, the
active pairs it holds. Cells cooperate only by passing messages to their four neighbours. The result is
the normal-form graph left in the cells' RAMs.

Status: **MVP**. It has a semantic golden model, a cycle-level fabric model, a frontend for a small
functional language, SystemVerilog RTL (Verilator) for 1×1 to 8×8 meshes, differential fuzzing under
randomised schedules, mutation testing and benchmarks. Local repo only, never pushed.

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
python3 -c "from omega import lang; print(lang.compile_source(open('programs/fib.olm').read().replace('N','10')))"
python3 tests/test_units.py --rtl        # directed rule tests on semantic + fabric + RTL 1x1/2x2/4x4
python3 tests/test_programs.py --fuzz 150
python3 tests/fuzz_rtl.py 0 600          # random nets, random meshes, random schedules
python3 tests/fuzz_rtl.py 0 200 --big
python3 tests/mutants.py                 # 16 RTL mutants
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
| `rtl/omega_pkg.sv` `omega_router.sv` `omega_cell.sv` `omega_mesh.sv` | RTL: encodings; 5-port XY router; cell (RAMs, shadow tags, free stacks, task stack, ROM, rewrite FSM); W×H mesh |
| `tb/tb_mesh.cpp` | testbench: reset, run to quiescence, dump |
| `programs/*.olm` | fib, sum, fact, list map/sum, tree build+sum, direct tree sum, insertion sort, quicksort, higher-order |
| `tests/` `bench/` `results/` | test suites, benchmarks, logs |

## Results

### Verification (final RTL, commit in "Commits" below)

| suite | result | what it checks |
|---|---|---|
| directed rule/unit tests (`tests/test_units.py --rtl`) | **35 / 35** | every rule of the rule table (25 hand-written nets with expected normal form *and* interaction count) + 9 frontend programs (closures, Church numerals, Ackermann, mutual recursion, `match`) + IR round trip. Each net runs on the semantic model (random, LIFO, FIFO order), the fabric model and the RTL on 1×1, 2×2, 4×4 with jitter/stalls and scattered loading |
| program tests (`tests/test_programs.py --fuzz 150`) | **268 / 268** | 9 programs × N = 0..5 (semantic), each program on the fabric model and on RTL 1×1/2×2/4×4 × 2 schedules, a performance bound (tree sum 4×4 ≥ 3× 1×1), and 150 random (program, N, mesh incl. 3×2 and 1×4, seed, jitter, stall, priority, scatter) cases |
| RTL differential fuzz, small nets (`tests/fuzz_rtl.py 0 600`) | **600 / 600** | random books (all node kinds, 3 DUP labels, all 16 operators with both flip bits, SWI, REF DAGs) on 1×1, 2×2, 4×4, 3×2, 1×4 with random arbitration seed, link jitter (0–63%), engine stalls, message/task priority and random scatter of `@main` over the cells. Readback, interaction count and live node count must equal the semantic model's (165 diverging nets rejected) |
| RTL differential fuzz, big nets (`--big`) | **FUZZBIG** | 3–8 definitions, 20–60 nodes each, ≥ 30 interactions |
| mutation testing (`tests/mutants.py`) | **MUTS** | 15 functional mutants of the rule logic / protocol / quiescence + 1 performance mutant (no work distribution, caught by the speed-up bound). Two mutants (eraser reaches only aux1; REF~DUP expands instead of copying) produce the *right* answer and are caught only by the node count / interaction count. That is why all three observables are compared |

Strong confluence is the test oracle. Any schedule (arbitration, delays, stalls, task/message priority,
initial placement) must produce exactly the same normal form, the same number of interactions and the
same number of live nodes. The fuzzers vary all of these on every run.

### Benchmarks (Verilator RTL, cycle accurate, 1024 node + 1024 var slots per cell)

BENCHTABLE

`*` = the program does not fit in one 1024-slot cell (a 512-leaf tree or a 120-element Scott list
needs > 1024 vars). The sequential baseline is therefore a single cell with 4096 slots. Speed-up is
cycles(1 cell) / cycles(W×H).

Observations:
* **Parallel recursion scales.** Direct tree sum (2¹⁴ leaves) reaches 3.99× on 4 cells, 15.7× on 16
  and 38× on 64. fib(20) reaches 3.99× / 13.7× / 25.7×. Up to 4×4, cell utilisation stays at 89–100%.
* **Sequential programs do not scale, and should not.** sum(1000) and fact(12) are a single dependency
  chain: ≈1.0× on every mesh. Lists are dominated by the sequential producer, and `list` gains nothing.
  qsort gains 5×, limited by the sequential partition passes. tree build+sum gains less than direct
  tree sum because building the tree is serial at the top.
* **Message traffic is low.** Demand-driven spawning keeps it at ≈0.002–0.11 messages per interaction
  up to 4×4 for the parallel programs. An earlier round-robin push policy needed ≈0.5 and could
  exhaust a 2×2 fabric's memory.
* **Cost per interaction.** One cell does 1 interaction per ≈5.3 cycles (IDLE pick + LINK + pushes +
  var links). A `link` through a var is the dominant cost, at about 1.5 per interaction.

### Comparison with TACHYON-128 (same algorithm: naive recursive fib(20))

| machine | work | cycles | vs TACHYON-128 |
|---|---|---:|---:|
| TACHYON-128 v6 (5-stage pipeline, BTB+RAS, tcc128 `-O`; `cpu128/README.md`, cc bench `fib`, includes `printf`) | 274,303 instructions, CPI 1.08 | **296,931** | 1.00 |
| TACHYON-Ω 1×1 | 295,525 interactions | 1,565,188 | 5.27× slower |
| TACHYON-Ω 2×2 | | 392,241 | 1.32× slower |
| TACHYON-Ω 4×4 | | 114,293 | **2.60× faster** |
| TACHYON-Ω 8×8 | | 60,948 | **4.87× faster** |

What this comparison does and does not say:
* **Per engine, Ω is about 5× worse than a pipelined von Neumann core.** A single cell needs about as
  many rewrites as the CPU needs instructions (295k vs 274k), and each rewrite takes ≈5.3 cycles against
  a CPI of 1.08. The fabric wins only through parallelism, which the program exposes *automatically*:
  the same source runs on any mesh with no threads, locks or scheduling code.
* **Cycles are not time or area.** The comparison does not cover clock frequency, area or energy, and
  Ω has no synthesis results yet.
  * Each Ω cell carries ≈330 Kbit of RAM (1024×128 b node + 1024×64 b var + 1024×130 b task stack) plus
    its FSM and router.
  * A 4×4 fabric is therefore far more silicon than one TACHYON-128 core (≈130k yosys cells, without
    memories).
  * An area-normalised comparison would also have to count the CPU's caches and DRAM, which the fabric
    does not need.
* **The numbers are 32-bit.** TACHYON-128 computes with 128-bit registers. Ω's NUM atoms are 32-bit.

## Known gaps

1. **Owner-capability security demo (optional item) is not implemented.** The port format reserves the
   4-bit owner field `[43:40]`, but no model sets or checks it. The planned design:
   * a per-slot shadow owner tag on node and var slots, inherited by every node and var a rewrite
     creates;
   * a trap when a LINK or NODE message reaches a slot whose owner differs from the incoming port's.
2. **RAMs are register files.** Node/var RAM, the free stacks and the task stack are reg arrays with
   asynchronous read and up to 4 writes per cycle (the commutation rule). That simulates and is
   synthesisable as flops, but a real cell would use 1R1W SRAM banks and take a few more cycles per
   rewrite. No yosys area numbers yet.
3. **Out-of-memory handling is detection, not recovery.**
   * Task-stack overflow (`err = 1`) or a 1×1 cell that cannot place an expansion (`err = 2`) halt the
     cell.
   * A globally full fabric can bounce SPAWNs (the RTL times out with status 3, and the Python model
     reports "no progress").
   * There is no spilling, and no back-pressure from memory to the spawn policy beyond the `hungry`
     wire.
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
   * No type checker.
   * DUP labels are allocated one per binder. Programs that duplicate closures that themselves
     duplicate can hit the usual interaction-combinator oracle problem; no such program is in the
     suite.
   * Arm lifting applies to `switch` and `match` only.
   * Results that are lazy references at the root (e.g. `def main = Nil`) read back as `@Nil`.
8. **Mesh flits are 266 bits wide** (one NODE message carries a whole 128-bit node plus two ports). A
   narrower physical link would serialise them into several flits.
9. **No optimal (Lamping/Δ-Nets) reduction.** Sharing is plain interaction-combinator duplication.

## Next steps (suggested)

1. Owner-capability tags and traps (Known gap 1), then two mutually distrusting programs on one fabric.
2. A banked SRAM cell (1R1W) and yosys/OpenROAD area and Fmax for one cell, giving an area-normalised
   comparison with TACHYON-128.
3. Cut the cycles per interaction:
   * overlap IDLE with the previous task;
   * process var links that need no message in the same cycle as the rewrite;
   * a 2-wide engine.

   ≈2.5 cycles/interaction looks reachable.
4. Smarter placement:
   * spawn depth limits and locality-aware NODE migration (move the smaller side);
   * memory-aware `hungry` (free-slot watermark);
   * spilling to a neighbour when full.
5. Bigger language: Latent/Bend subset with `fold`/`bend`, signed numbers, strings, and a typed
   front end. A TACHYON-128 host interface (DMA of graph images, result readback).

## Commits

COMMITS
