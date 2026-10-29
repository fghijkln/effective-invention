# Step 14 exploration (branch explore-variance): seed variance + governor — fabric model only

Baseline: bd6b226 (step 13). Everything here is the Python cycle model `omega/fabric.py`
(p_msg 0.5, 1024-slot cells, qdepth 4096). No RTL/Verilator run. Absolute fabric-model cycles are
not the RTL numbers (treesum(9) 8×8 fabric 3,920–6,665 vs RTL 2,139–2,652); the comparison is relative.
Tables: `results/var/final_tables.md` (generator `bench/var_final_report.py`, raw `full.jsonl`, `t16.jsonl`).
Semantic check: every run compares readback + interaction count with the semantic reducer (all `ok`);
`tests/test_fabric_var.py` (1×1/2×2/3×2/4×4/8×8, jitter/stall, scattered images, 256-slot cells).

## Root cause of treesum(9) 8×8 seed variance

* Probe (`var_probe.py`, `probe_sources.log`): the spread phase is seed-independent (16 cells busy at
  ~270–300 cycles every seed); the variance lives in the **tail**. Splitting the RNG: engine visit order
  (sd 621) ≥ router arbitration (409) > coin flips (300) — any small arbitration difference is amplified.
* Timeline (`probe_timeline.log`, `probe3_bot3d4.log`): after ~1,200 cycles busy cells fall to 10–30 of 64
  while fork tasks still wait. Two mechanisms:
  1. **LIFO give**: the task stack is a pure stack, so a hungry neighbour receives the *newest* (small,
     deep) subtree; the big shallow subtrees sit at the bottom of a few busy cells and are run serially.
     Which cells end up holding them is decided by arbitration order → long, seed-dependent tail.
  2. **Hunger is only visible to direct neighbours**: up to ~40 idle cells are "stranded" (no neighbour
     holds fork work although fork work waits elsewhere).

## Fix (hardware-friendly)

* **s14c — fork deque + bottom give** (`bot_give=3, fdepth=4`): a 4-entry side deque per cell holds ready
  fork-REF redexes; the engine pops the main stack first, then the newest fork task; a hungry neighbour gets
  the *oldest* fork task via SPAWN. Fixes mechanism 1.
* **s14b — + hunger gradient with relay** (`grad=3, dmin=3`): a 2-bit saturating hunger distance per cell
  (0 = hungry, else 1+min of neighbours, cap 3); with ≥3 fork tasks queued a cell gives downhill, and a busy
  cell receiving a fork SPAWN while it has a downhill neighbour parks it on its deque (relay). Fixes 2.
* **Governor nb5l1** (`gov_nb=5, gov_l0=1`, in s14c and s14b): at epoch end a cell with a hungry neighbour
  relaxes one level while under 1.25× budget (instead of tightening when over budget); reset level 1
  (threshold 2) instead of 2. Only producer-recursion programs (qsort/list/sort/higher) are affected;
  s14c and s14b are cycle-identical there.

## Key results (mean, Δ vs base, sd/range, [msgs/int])

treesum(9) 8×8, 16 seeds: base 5,044 sd 750 range 2,745 [0.44] → s14c 4,171 (−17%) sd 304 (−59%) range 1,102
(−60%) [0.46]; s14b 3,776 (−25%) sd 256 (−66%) range 870 (−68%) [0.57].
treesum_direct(14) 8×8: −33% (s14c) / −39% (s14b), sd −83%/−94%; fib(20) 8×8 −26% / −29%. No regression anywhere.
qsort(40) 4×4: base 21,534 [0.42], fixed kp=4 19,770 (−8.2%) [0.52], s14c/s14b 19,214 (−10.8%) [0.47] →
governor now beats kp=4 by 2.8% while staying under 0.5 msgs/int. 8×8: −16.2% [0.50] (kp4 −13.1% [0.53]).
list 4×4/8×8 −10.2%/−6.9% [0.48/0.52]; sort −19.3%/−14.8% [0.50/0.52]; higher −6.9%/−12.2% [0.62/0.65].
4×4→8×8 speed-up for sort/list/higher stays ≈1.0–1.1× under every config: the gains are equal on both meshes,
the scaling wall is the programs' limited parallelism, not distribution. Fork programs scale much better
(treesum_direct 2.20× → 3.41×, fib 2.53× → 3.41×).

## Verdict / RTL cost (estimate, not synthesised)

* Worth RTL: **fork deque + bottom give + nb5l1 governor (s14c)** — meets the variance target alone
  (sd/range −59/−60%), mean better everywhere, msgs/int unchanged on fork programs. Cost per cell: 4-entry
  task register file (~4×72 b ≈ 300 flops), fork-task classifier reusing the step-11 fork bit, a pop/give mux,
  and a comparator in the governor epoch logic; rough < 1% of omega_cell area (≈150k µm² std-cell part),
  no critical-path concern expected.
* Optional: hunger gradient + relay (s14b) — another −8 to −10% on 8×8 fork programs, but treesum(9) 8×8 goes
  0.45 → 0.55 msgs/int and adds 2-bit hd registers + 4 neighbour wires + relay path in SPAWN receive. Adopt
  only if 8×8 fork throughput matters more than message budget.

Semantic regression: `tests/test_fabric_var.py` all 20 configs 1620/1620 pass (results/var/test_all.out); all sweep runs ok vs semantic reducer.
