# Step 25 status: symbolic B(N) + admission control

- 14:45 CST 2026-11-01: base 7187b58 (step 24). Sandbox restarted again (no verilator, /tmp/omega_build lost): toolchain setup started (results/s25/setup.log).
- 14:55: toolchain ready; reg.sh started (results/s25/reg.status; resumable). No fabric.py / RTL / tb change planned (admission is a separate layer), so defaults stay identical by construction.
- 15:40: omega/symbolic.py (BM + exact closed forms, envelope fallback), omega/causal.py (W_nodes lib + W_vars), omega/admission.py (Scheduler), tests/test_s25.py written; quick sections green. Full test_s25 running (s25_full.log).
- 16:20: test_s25 mutants 6/6 caught (s25_mutants.log). Running sym_all.sh (symbolic.log, sort_decomp.log, wvars.log) then final full test_s25 (s25_full.log). reg: id 128/128, units 42, programs 315, s14 90 so far.
- 16:50: WIP 0463868 pushed (docs drafted: SPEC §7.3/§7.4, README step-25 section, gaps 13/14, next step 3, commits line has REGRESSION_PLACEHOLDER). after.sh waits for reg.done then runs test_eal + eal mutants. Final full test_s25 2749/2749 (s25_full.log), mutants 6/6.
- 16:58: mutants 37-54 started in parallel (mutc.sh -> mutCres line), as in step 24.
- 16:35 (approx): sandbox restarted (toolchain lost) after fuzz 600/600; reg.sh resumed (setup again; bigfuzz next), mutc.sh waits for ~/env.sh.
- 17:10: the parallel mutc.sh and reg.sh built the same /tmp/omega_build dir at once (PCH collision): bigfuzz / security failed to build (not test failures); mempress finished 60/60 (1452 s). Dropped those two lines, reg.sh restarted with OMEGA_BUILD=/tmp/omega_build_reg (separate build dir) while mutc continues (mutants 37-41 caught so far).
- 17:35: mutC 18/18 caught (37-54). reg.sh (bigfuzz) continues with its own build dir; mutants 19-36 started in parallel (mutb.sh, OMEGA_BUILD=/tmp/omega_build_mb).
- 17:58: sandbox restarted again (toolchain lost, nothing running). Resuming serially with run2.sh: setup -> reg.sh (bigfuzz, security, mutA 0-18) -> mutb.sh (27-36 left; 19-26 caught) -> after.sh. Logs reg.out4, mutb.out2, after.out; run2.log.
- 18:30: bigfuzz 200/200 (1683 s), security 420/420. mutA (0-18) running, then mutb.sh 27-36, then after.sh (run2.sh).
- mutA 19/19 caught (0-18); mutb.sh (27-36) running, then after.sh.
- ~18:55: sandbox restarted again during mutb (19-26 caught, 27 in progress). Resumed with run3.sh: setup -> mutb.sh -> after.sh.
- 19:3x: all done: mutB 18/18 (19-36), eal 597/597, ealmut 7/7. README placeholder filled; committing step 25.
