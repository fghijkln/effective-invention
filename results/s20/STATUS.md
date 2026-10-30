# Step 20 status — DONE

Final: slot reserve 4 -> 1 (`+rsv` / `OMEGA_RSV`, default 1; `+rsv=4` = step 19 cycle for cycle), SPEC §7.1 progress
argument + counterexample, fabric probe knobs (default off), mutant 51, README step-20 section.

History:
- WIP commit 60f92c3 pushed (CI green) with the code, SPEC, README section and the first half of the regression.
- Mutant 51 (reserve applied without a downhill neighbour): first kill threshold keep 45 did not separate design and
  mutant on RTL; results/s20/minkeep_rtl.py found the RTL minimum, keep 93 (fib(10) 1x1, correct design status 0,
  mutant status 2) -> mut51.txt 1/1 caught.
- Sandbox restarted at ~15:00 UTC during the full mutant run (mutants 0..30 done, saved as mutants_part1.txt);
  toolchain rebuilt (tc_setup2.log), reg2.sh ran 31..51 (mutants_part2.txt) and merged into results/mutants.txt.
- Mutant 50 (step-19 full-cell pass-on off) SURVIVED at the new default +rsv=1: global treesum(7) 8x8 seeds 16/18
  now finish without the pass-on. Detector strengthened: runs the seeds at +rsv=4 first (= step 19, where both stop),
  then +rsv=1; rerun (mut50.txt) caught at seed 16 and 18 +rsv=4. The pass-on stays required for +rsv=4 and is the
  rule SPEC §7.1 relies on; no default-config (+rsv=1) killing case was searched for — open item.

Regression (reg.status): identity 128/128, units 42/42, programs 315/315, s14 90/90, fuzz 600/600, big 200/200,
security 420/420, mempress 44/44, mutants 52/52.
