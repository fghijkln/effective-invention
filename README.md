# TACHYON-Ω — a Spatial Interaction-Net Fabric

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
| `rtl/omega_pkg.sv` `omega_router.sv` `omega_cell.sv` `omega_mesh.sv` | RTL: encodings; 5-port XY router; cell (RAMs, shadow tags, free stacks, task stack, ROM, rewrite FSM); W×H mesh |
| `tb/tb_mesh.cpp` | testbench: reset, run to quiescence, dump |
| `programs/*.olm` | fib, sum, fact, list map/sum, tree build+sum, direct tree sum, insertion sort, quicksort, higher-order |
| `tests/test_security.py` | owner-capability isolation: multi-tenant demos, attacks, fault injection, multi-tenant fuzz |
| `tests/` `bench/` `results/` | test suites, benchmarks, logs |

## Results

### Verification (final RTL, commit in "Commits" below)

| suite | result | what it checks |
|---|---|---|
| directed rule/unit tests (`tests/test_units.py --rtl`) | **35 / 35** | every rule of the rule table (25 hand-written nets with expected normal form *and* interaction count) + 9 frontend programs (closures, Church numerals, Ackermann, mutual recursion, `match`) + IR round trip. Each net runs on the semantic model (random, LIFO, FIFO order), the fabric model and the RTL on 1×1, 2×2, 4×4 with jitter/stalls and scattered loading |
| program tests (`tests/test_programs.py --fuzz 150`) | **268 / 268** | 9 programs × N = 0..5 (semantic), each program on the fabric model and on RTL 1×1/2×2/4×4 × 2 schedules, a performance bound (tree sum 4×4 ≥ 3× 1×1), and 150 random (program, N, mesh incl. 3×2 and 1×4, seed, jitter, stall, priority, scatter) cases |
| RTL differential fuzz, small nets (`tests/fuzz_rtl.py 0 600`) | **600 / 600** | random books (all node kinds, 3 DUP labels, all 16 operators with both flip bits, SWI, REF DAGs) on 1×1, 2×2, 4×4, 3×2, 1×4 with random arbitration seed, link jitter (0–63%), engine stalls, message/task priority and random scatter of `@main` over the cells. Readback, interaction count and live node count must equal the semantic model's (165 diverging nets rejected) |
| RTL differential fuzz, big nets (`--big`) | **200 / 200** | 3–8 definitions, 20–60 nodes each, deeper trees, more references; only nets with ≥ 30 interactions are kept (avg 375, max 16,239 interactions; 4,088 candidates rejected as diverging or trivial) |
| owner-capability isolation (`tests/test_security.py --fuzz 300`) | **420 / 420** | 2- and 4-tenant program demos (fib ∥ qsort; treesum ∥ list ∥ sort ∥ higher-order) on 1×1/2×2/4×4/3×2, each tenant gets its known answer with zero traps; 10 attack programs (overwrite / capture the victim's result through a forged root-var pointer, out-of-bounds slot and cell, forged node pointers to the victim's result node, an attack hidden in a lazily expanded definition) and 3 cross-owner fault injections, each with the sender-side check on and off (`fi`); 300 random multi-tenant cases (2–4 random tenants, random owners, half with an attacker carrying random forged redexes). Semantic model, fabric model and RTL must agree on every honest tenant's result and node count, on the trap set and on the interaction count (SPEC §12) |
| mutation testing (`tests/mutants.py`) | **29 / 29 caught** | 15 functional mutants of the rule logic / protocol / quiescence + 1 performance mutant (no work distribution, caught by the speed-up bound) + 6 security mutants (each owner-capability check disabled, owner stamping missing, trap not blocking). Two mutants (eraser reaches only aux1; REF~DUP expands instead of copying) produce the *right* answer and are caught only by the node count / interaction count. That is why all three observables are compared. + 5 v3 engine mutants (read-ahead write bypass, write-queue drain, var owner-tag queue, allocation pop count, ROM read-ahead) + 2 memory-pressure mutants (caught by `tests/test_mempress.py`) |

Strong confluence is the test oracle. Any schedule (arbitration, delays, stalls, task/message priority,
initial placement) must produce exactly the same normal form, the same number of interactions and the
same number of live nodes. The fuzzers vary all of these on every run.

### Benchmarks (Verilator RTL, cycle accurate, 1024 node + 1024 var slots per cell)

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
| TACHYON-128 core v4 (`cpu128/results/synth_stat_abc.txt`) | 129,811 | 8,519 | 217,636 | 3 macros (register file ≈ 26 Kbit) |

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

1. **Owner capabilities: scope.** 15 tenants (4-bit owner, 15 = free). A trapped tenant is not
   killed or cleaned up: its offending operation is dropped and the rest of its graph may stay in
   memory (no reclamation of a misbehaving tenant's slots). There is no timing isolation: tenants
   share cells, routers and memory capacity, so one tenant can slow another or exhaust shared memory.
   The ROM is shared, so tenants see each other's definitions (they cannot forge an owner, but code is
   not confidential). Forged pointers to slots the attacker itself owns are not trapped (no isolation
   issue, but the attacker can corrupt its own graph).
2. **Synthesis is technology-independent.** Generic-gate cell counts and NAND2 equivalents only; no
   standard-cell library, no place and route, no timing. Memories are counted in bits, not area.
   The per-slot `nalloc` valid bits are flip-flops (1 per node slot) and dominate the growth from
   256 to 1024 slots.
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

* `9322771` stage 0: port encoding, text IR, semantic reducer
* `6d68b69` stage 1: cycle-level fabric model (cells, mesh routers, LINK/NODE/SPAWN protocol, retry back-pressure, loader image)
* `cb05aa5` stage 2: Omega-lang frontend (lambda + numbers + recursion + Scott data, arm lifting) and program suite
* `fc3d68d` stage 3+4: SystemVerilog RTL (active memory cell, 5-port mesh router, W x H mesh), Verilator TB, Python harness; programs pass on 1x1/2x2/4x4
* `2a4c82c` stage 5a: random net generator, RTL differential fuzz (600/600), directed unit tests (35/35 incl. RTL), mutation knobs + harness
* `759fc50` stage 5b: mutation testing 16/16 caught, SPEC.md, program tests, bench script
* `7be478c` frontend: only lift arms that can reduce (value arms inline) - fixes unexpanded REF results at N=0; program tests 268/268
* `18e4ce5` demand-driven spawn (hungry side-band wires between neighbours) replaces round-robin push: 100x fewer messages, no OOM livelock; per-cell peak occupancy counters; run_all.sh
* `9cccae8` full regression on demand-driven spawn RTL: units 35/35, programs 268/268, fuzz 600/600 + big 200/200, mutants 16/16; README draft
* (HEAD) benchmarks with demand-driven spawn, README/SPEC final
