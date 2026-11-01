# Step 24 status: Ω-L, a light-affine typed subset with a compile-time peak-memory bound

- 11:50 CST 2026-11-01: base 03dad19 (step 23). Sandbox had restarted: toolchain setup re-running (results/s24/setup.log).
- Plan: omega/eal.py (checker on the lifted/resolved AST + HM binder types; bound = initial + sum of positive node deltas / var allocations
  over the schedule-independent interaction multiset, counted at compile time; growth class per SCC), `python3 -m omega.eal` CLI,
  tests/test_eal.py (accept/reject units, bound >= measured peaks semantic/fabric/RTL 1x1, typed fuzz, RTL with free slots = bound), checker mutants.
- 12:00–12:40: omega/eal.py written (checker T/A/!/R on HM types with monomorphic fields + resolved templates; counting-run bound;
  growth classes; CLI `python3 -m omega.eal`). tests/test_eal.py: checker units (15 accept / 17 reject), census (18/24: 8/9 programs,
  10/15 LANG), bound checks (order independence, recount, semantic 5 orders, fabric 1x1/2x2/4x4), RTL sections, typed fuzz, 7 eal mutants.
  --no-rtl --fuzz 60 green; --mutants 7/7 caught. results/s24/worst.py: causal bound W (max closure, Dinic) -> worst.log
  (B/W 1.7-2.9, sort 9.2; W identical from 6 recorded orders). SPEC text drafted in results/s24/spec_72.md.
- reg.sh (results/s24/reg.status) started 11:55, id8 8x8 build running; RTL parts of test_eal wait for it (memory).
- 13:10: docs in SPEC §7.2 / §7.1(3) / §10, README step-24 section + table (results/s24/table.md), gap 13, next step 3, CI quick + run_all add test_eal. Reg: id 128/128, units, programs 315, s14 90, fuzz 600 green so far. Final test_eal + eal mutants running (eal_final.log, eal_mutants.log).
- 13:35: final test_eal 597/597 (eal_final.log), eal mutants 7/7 (eal_mutants.log). Waiting on reg (bigfuzz, security, mempress, mutA-C).
- 13:55: WIP 6240add pushed, CI 41274422186 success. reg: bigfuzz 200/200, security 420/420; mempress running; mutants 37-54 run in parallel (mutc.sh -> mutCres line), 0-36 by reg.sh.
- 14:00: sandbox restarted (toolchain + builds lost); resumed reg.sh (setup again) and mutc.sh (resumes after mutant 38).
- 14:35: reg ALLDONE: id 128/128, units 42/42, programs 315/315, s14 90/90, fuzz 600/600, big 200/200, security 420/420, mempress 60/60, mutants 0-18 19/19, 37-54 18/18; 19-36 running (mutb.sh).
- 14:55: all done: mutants 55/55 (19+18+18). Final commit + push next.
