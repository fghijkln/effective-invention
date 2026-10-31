# Step 21/22 status (2026-10-31)

Step 21 (tests only): mempress ballast keep 0/8 added (10 cases -> 54); mutant 50 detector at default +rsv=1
(fib(12) 2x2, treesum(6) 3x2 keep 0/8); fabric knob OMEGA_PASSON. RTL check results/s21/rtl_k0.log 10/10 vs mutant 10/10 stuck.
README section + table rows + SPEC line done. Regression: results/s21/reg.sh (resumable via reg.status).
Sandbox restarted twice (13:4x and ~15:00 CST); toolchain via /workspace/work/setup_tc_noyosys.sh.

Step 22 (fabric probes, knobs in omega/fabric.py, all default off):
- ADM bit0 shrink-first (HVM2 idea): cex K=200 still 20/20 stuck.
- ADM bit1 no-give in lowmem (LM_T=-1 or huge): still 20/20 stuck (forwarding on no-room spreads anyway).
- ADM bit3 low-memory mode (no cell ample -> roomy = abs 64/32, reserve 16): trigger SLOTS/4: K=120/150/200 0/20, K=300 9/20 (= default).
  trigger SLOTS/2 (LM_AHI=512): K=200/300/500 0/20.
- ADM 24 (always strict): K=200/300/500 0/20; global perf: treesum(6) 3x3 13,624 (+1.0%), list(20) 3x2 6,943 (+12.6%), fib(12) 6x6 33,706 (+1.8%) = step 19 numbers.
- Benchmarks (fabric 4x4/8x8, 9 progs x 2 seeds): ADM 24 identical cycle for cycle (bench_adm0/24.jsonl).
- Default: K=300 9/20 stuck, K=500 1/20 stuck.
- RTL implementation drafted in worktree /workspace/work/omega-wt-s22 (branch s22-wip): lm_mode/lm_hi/lm_lo/lm_rsv inputs, ample OR tree in mesh.
