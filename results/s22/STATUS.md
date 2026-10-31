# Step 22 merge status (2026-10-31)

- 17:50 CST: worktree s22-wip files copied onto main 22699cc (fabric.py/mutants.py/test_mempress.py in the worktree
  already carried the step-21 changes; rtl/tb/rtl.py untouched by step 21). README/SPEC via results/s22/apply_docs.py.
- Smoke: results/s22/near_smoke.log (RTL treesum(9) 3x3 corner 500 seed 9, lm 0 vs 2), results/s22/ci_quick.log.
- Full regression: results/s22/reg.sh -> results/s22/reg.status (resumable).
- ~19:00 CST: smoke OK (RTL near seed 9: lm=0 status 3, lm=2 status 0 in 49,193 cycles); ci_quick OK.
  Regression: identity 128/128 (lm=2 default, cycle-identical to step 15 refs), units 42/42, programs 315/315,
  s14 90/90, fuzz 600/600, bigfuzz 200/200, security 420/420, mempress 56/56. Mutants running.
  Decision: lm=2 stays default (no benchmark change at all).
- sandbox restart during mutants (~19:05 CST); reg.sh relaunched (resumes at mutants)
- 2nd sandbox restart (~19:58 CST) after mutant 38; mutants 0-38 caught (results/s22/mut_part1.txt); rest via results/s22/mut_rest.sh -> mut_rest.txt
