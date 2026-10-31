### Low-memory watermarks: the step-20 counterexample finishes (step 22)

Step 20 showed that the default can stop with *enough* memory in total (SPEC §7.1, treesum(9) 3×3: 8 cells
with 8 free node / var slots, the corner with 200, stalls 20 / 20 on the fabric model). Step 22 tries
memory-aware admission on the fabric model, adopts the one rule that fixes it, and puts it in the RTL as the new
default: **low-memory watermarks** (`+lm` / `OMEGA_LM`, default 2; `+lm=0` = step 21 cycle for cycle).

* `roomy` uses absolute watermarks, set at ≥ 64 free node and var slots and cleared below 32 (`+lmhi`, `+lmlo`),
  instead of SLOTS/4 / SLOTS/8 (256 / 128). A corner with a few hundred free slots is now room, so the gradient
  points at it.
* With room downhill an expansion must leave **16** slots free (`+lmrsv`) instead of `rsv` = 1, so a poor cell no
  longer starts a 5–6-node definition of its own; work collects where the room is and is reduced there depth
  first.
* `+lm=1` engages both only while no cell is *ample* (≥ SLOTS/2 free, cleared below SLOTS/4): a registered OR tree
  over one bit per cell, like the quiescence tree. It ships as a knob (see below why it is not the default).

Without pressure every cell stays above 64 free slots, `rdist` stays 0 and nothing changes: the 9 standard
programs on 4×4 and 8×8 (2 seeds each, fabric model, `results/s22/bench_adm0.jsonl` / `bench_adm24.jsonl`) and
the 128-run RTL identity check (step-15 references) are cycle-identical.

**Fabric model, treesum(9) 3×3, 8 cells with 8 free slots, corner with K, 20 seeds: runs that stop**
(`results/s22/cexk.log`, `cexv.log`, `cexw.log`; `+lm=1` (SLOTS/4) is a first trigger that only engaged once the
corner fell below 128):

| corner K | step 21 (`+lm=0`) | `+lm=1`, trigger SLOTS/4 | `+lm=1`, trigger SLOTS/2 | **`+lm=2` (default)** |
|---:|---:|---:|---:|---:|
| 120 | 20 | 0 | – | **0** |
| 150 | 20 | 0 | – | – |
| 200 (step-20 counterexample) | **20** | 0 | 0 | **0** |
| 300 | 9 | 9 | 0 | **0** |
| 400 | 7 | – | – | – |
| 500 | 1 | – | 0 | **0** |
| 600 | 1 | – | 1 (corner ample: never engages) | – |
| 800 | 0 | – | – | – |
| 1024 (mempress global treesum(9)) | 0 | – | – | **0** |

Finished runs take 109,507 cycles under `+lm=2`, the 1×1 time with the same memory (109,463): the work runs
almost sequentially in the corner, which is what a fabric this full can afford.

Other programs, near-overfull (corner keeps f × the program's 1×1 peak + 8, the others 8 / 8, fabric, 10 seeds,
`results/s22/near.py`): at f = 1.3 the default stops on **10 / 10** runs of fib(12), treesum(7) and
treesum_direct(8), at f = 2.0 on 10 / 10 of fib(12) and treesum_direct(8) and 9 / 10 of treesum(7); qsort(15),
list(20), sort(10), higher(30) finish. With `+lm=2` (and `+lm=1`) all 140 runs finish.

**RTL.** The RTL reduces in a different order: after an expansion it links the root to its partner at once
(`S_EXN` → `S_LINK`), while the fabric model pushes the root link below the definition's redexes, so the RTL builds
treesum's tree ahead of the sum and a 1×1 RTL cell needs **451–470** free slots for treesum(9) (fabric model: 115;
`results/s22/rtl_1x1.py`). With 200 in the corner the case is simply overfull for the RTL (status 3 in every
mode). The RTL counterpart (`results/s22/rtl_cexK.log`, 30 seeds each):

| corner K | step 21 (`+lm=0`) | `+lm=1` | **`+lm=2`** |
|---:|---:|---:|---:|
| 470 | 1 / 30 (seed 9) | 0 | **0** |
| 500 | 1 / 30 | 0 | **0** |
| 600 | 1 / 30 | 1 / 30 | **0** |
| 800, 1024 | 0 | 0 | **0** |

**Cost under global pressure** (the step-20 cases, corner fully free, 8 / 8 elsewhere): RTL 13 seeds
(`results/s22/rtl_big.jsonl`) list(20) 3×2 3,114 → 3,236 cycles (+3.9%, i.e. step 20's gain there is given back),
fib(12) 3×3, treesum(6) 3×3, qsort(15) 4×4, sort(10) 3×3 within ±0.2%; fabric model 20 seeds (`results/s22/perf.log`)
treesum(6) 3×3 +1.0%, list(20) 3×2 +12.6%, fib(12) 6×6 +1.8% (the step-19 numbers: a ballast cell with 8 free slots
again sends every expansion on).

**Why not `+lm=1` (cheaper on pressure, the OR tree costs a wire per cell):** it only engages once *no* cell has half
its slots free, and the stopping runs above happen with corners at 500–600 free slots too (fabric K = 600, RTL
K = 600: 1 / 30). Any fixed trigger leaves such a window; the absolute watermarks need no trigger.

**Rejected probes (fabric model, K = 200, 20 seeds, all stop 20 / 20):**
* *shrink-first* (HVM2-style "work before grow"): a cell that is not roomy pops, from the top 4 stack entries,
  annihilations / erasures before neutral tasks and before commutations, REF expansions and SPAWNs
  (`OMEGA_ADM=1`). In the stopped state every pending task is a SPAWN, so there is nothing to prefer; earlier on it
  does not lower the peak enough.
* *no gives in low memory* (`OMEGA_ADM=2`, with the fabric-wide free count or "no cell roomy" as the signal; with it
  always on the run is sequential and has the 1×1 peak): a SPAWN that does not fit still moves to a neighbour and
  starts a new depth-first thread there, so the parallel spread comes back through the no-room path.

The probes stay as fabric knobs (`OMEGA_ADM`, `OMEGA_ADM_W`, `OMEGA_LM_T`, `OMEGA_LM_AHI`), default off.

**Tests.** `tests/test_mempress.py` gets the near-overfull case (treesum(9) 3×3, corner 500: fabric seed 14 and RTL
seed 9, both stop at `+lm=0`; mempress 54 → 56). Mutant 52 (low-memory watermarks never engage) is caught by it.
Area: two 8-bit comparator pairs and the ample comparators per cell, a 5-bit reserve mux, one OR tree; not
synthesised.

**What it does not give:** still no completion *guarantee*. The rule makes the parallel peak track the room
(work collects in roomy cells and runs depth first there) but a program whose depth-first order on one cell needs
more than any cell has, or memory spread thinner than 64 slots per cell, can still stop (detected, status 3).
