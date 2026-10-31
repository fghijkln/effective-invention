# Step 23 status: +ilr (internal redexes before the root link of an expansion), RTL only

- 21:40 CST: base ec9ea3f (step 22). Edits: rtl/omega_cell.sv (ex_ilr/ex_ilr0: the first writing S_EXN cycle pushes
  {K_LINK, x, TR(root)} below the redexes; last cycle fin / S_IDLE instead of S_LINK root; MUT[53] ignores the knob),
  rtl/omega_mesh.sv + tb/tb_mesh.cpp (+ilr, tb default 1), omega/rtl.py (+ilr=fabric.ILR), omega/fabric.py (ILR from OMEGA_ILR, default 1).
- smoke: fib(10), treesum(5) 1x1 correct with ilr=1.
- 22:05: 1x1 treesum(9) peaks (rtl.run cells peak_nodes/peak_vars): ilr=0 281/463, ilr=1 159/238, fabric model 75/118.
  Gap after ilr=1 = child order (fabric probe results/s23/fab_order_probe.py: model with RTL child order 157/252).
  Added ilr=2: also the model's child order (copy/erase, annihilation, commutation continue with the LAST link). ilr=2: 73/123, cycles 49,385 (ilr=0 49,199, ilr=1 49,141).
- 22:40: benchmarks 1x1/2x2/4x4 x 8 seeds (results/s23/b4_ilr{0,1,2}.jsonl, cmp.py): ilr=1 list(120) +31%, higher(100) +22..38% on 2x2/4x4
  (geo mean +1.8%); ilr=2 geo +3.0%. 1x1 peaks (vars) ilr0/1/2: treesum 463/238/123, qsort 769/848/1282, fib 158/269/278,
  list 2172/1780/1686, higher 1519/1523/1226, sum(1000) 3008/3010/4005 -> order is program-dependent, not a general win.
  Tried adaptive ilr=3 (2 while cell not ample): qsort(40) 1x1 peak 769 -> 981 => dropped.
  DECISION: knob only, default +ilr=0 (= step 22 exactly). sum(1000) 1x1 under ilr=1/2 needs qdepth 4096 (stack 2003).
- thresholds (results/s23/thr.py): treesum(9) 1x1 needs ilr2 120, ilr1 235 (ilr0 451-470 per step 22). thr.sh running for ilr0 + mutants.
- added: mempress run_ilr (ILR_CASES K=130 ilr=2, K=250 ilr=1; fabric+RTL), mutants 53/54.
- b8_ilr1 8x8 sweep running orphaned (bench.sh killed); b8_ilr2 still to run.
- 22:30–01:30 CST: verified defaults (fabric/rtl/tb all +ilr=0). reg.sh: identity 128/128, units 42/42,
  programs 315/315, s14 90/90, fuzz 600/600, big 200/200, security 420/420, mempress 60/60; k2 units 42/42, programs 315/315,
  fuzz 600/600, big 199/200 (case 3420 1x1: var slots exhausted under ilr=2, status 3; correct with 4096 slots, peak vars 1106,
  ilr0 703 -> k2_bigfuzz_3420.txt); k1 units 42/42, fuzz 600/600, big 200/200. Mutants run in two parallel jobs (mut_par 0-27,
  mut_a 28-41, mut_b 42-54). b8 8x8 knob sweeps skipped (optional). cmp.py geo mean (24 cells 1x1/2x2/4x4): ilr1 +5.4%, ilr2 +7.1%.
