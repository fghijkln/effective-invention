### Expansion order: internal redexes before the root link (step 23)

Step 22 found that the RTL and the fabric model reduce in different orders: after an expansion the RTL linked the
definition's root to its partner at once (`S_EXN` → `S_LINK`), while the model pushes the root link *below* the
definition's redexes. So a 1×1 RTL cell needed 451–470 free slots for treesum(9), against 115 on the model. Step 23
adds the model's order to the RTL as a run-time knob, **`+ilr` / `OMEGA_ILR`** (SPEC §5, "Expansion order"):

* `+ilr=0` (**default**): step 22, cycle for cycle (identity check: 128 / 128 runs identical to the step-15
  references).
* `+ilr=1`: if a definition has at least one redex, the first writing `S_EXN` cycle pushes the root link under that
  cycle's redexes. The internal redexes, and everything they push, are reduced before the root is linked.
* `+ilr=2`: also the model's **child order**. Erase / copy, annihilation and commutation go on with their *last* new
  link and push the others (step 22 goes on with the first), so tasks pop in the model's order.

**Peak slots, one 1×1 cell** (`rtl.run` peak node / var slots; bisection of the free slots treesum(9) needs, in a 1×1
cell with K free node and K free var slots: `results/s23/thr.py`, `thr.log`):

| | `+ilr=0` (step 22) | `+ilr=1` | `+ilr=2` | fabric model |
|---|---:|---:|---:|---:|
| treesum(9): peak nodes / vars | 281 / 463 | 159 / 238 | **73 / 123** | 75 / 118 |
| treesum(9): free slots needed | 460 | 235 | **120** | 115 |
| qsort(40): peak vars | 769 | 848 | 1,282 | |
| fib(20): peak vars | 158 | 269 | 278 | |
| list(120) / higher(100): peak vars (4,096 slots) | 2,172 / 1,519 | 1,780 / 1,523 | 1,686 / 1,226 | |
| sum(1000): peak vars, task-stack depth (4,096 slots and entries) | 3,008, 1,005 | 3,010, 2,003 | 4,005, 2,003 | 4,009, 2,005 |

`+ilr=1` alone halves treesum's peak. The rest of the gap is the child order, not the root link: the model with
the RTL's child order (`results/s23/fab_order_probe.py`, which reorders the model's rule pushes) peaks at
157 / 252, the same as `+ilr=1`, and `+ilr=2` matches the model. But the better order depends on the program. treesum
builds a tree that the deferred root keeps from growing ahead of the sum. In qsort, fib and sum the "internal"
redexes are the recursive calls, so deferring the root makes the cell go deep before it combines anything. sum(1000)
keeps one deferred root link per level, so its task stack doubles (it then needs `qdepth` 4,096 on 1×1; with 1,024
it stops with `err` 2, never with a wrong answer).

**Cycle cost** (standard benchmarks, 8 seeds each, mean cycles; step 22 = `results/s23/id_*.jsonl` and
`b4_ilr0.jsonl`, the knob runs `results/s23/b4_ilr{1,2}.jsonl`, `b8_ilr{1,2}.jsonl`; table from `results/s23/cmp.py`;
sum(1000) on 1×1 is from the 4,096-entry stack runs, `results/s23/sum1x1_q4096.json`):

CMP_TABLE

On one cell the order costs a few percent either way (fib(20) +2.3% / +4.4%, sum(1000) −6.9% at `+ilr=1`).
With more cells, list(120) and higher(100) lose 22–38% at both settings: the root link is what hands a
producer's result to its consumer, so deferring it holds back the work it would give to the neighbouring cells.
That is well beyond the seed-to-seed spread of the 8-seed means.

**Decision: `+ilr` stays a knob, default 0.** The benchmarks regress (list and higher on 2×2 / 4×4 / 8×8), and the
peak-memory gain is specific to treesum-like programs (qsort, fib and sum peak higher). An adaptive variant was
tried and dropped: the `+ilr=2` order only while a cell is not *ample* (fewer than SLOTS/2 free slots). It left
treesum(9) 1×1 at 1,024 slots unchanged (the cell never drops below the clear watermark) and raised qsort(40) 1×1
from 769 to 981 peak vars (+1.5% cycles), because qsort crosses the watermark and then goes deep.

**Tests.** `tests/test_mempress.py` gets the expansion-order cases (4): treesum(9) on one cell with 130 free slots
at `+ilr=2` and with 250 at `+ilr=1`, on the fabric model and the RTL (step 22 order: status 2, out of memory).
Mutants **53** (the root is linked at once whatever `+ilr` says: needs 460 / 470 free slots, caught by both cases) and
**54** (`+ilr=2` without the child order: needs 235, caught by the 130 case). The knob settings also pass the
correctness suites: `+ilr=2` units K2UNITS, programs K2PROGRAMS, fuzz K2FUZZ + big K2BIG; `+ilr=1` units K1UNITS,
fuzz K1FUZZ + big K1BIG (`results/s23/k*_*.log`).
