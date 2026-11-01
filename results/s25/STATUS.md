# Step 25 status: symbolic B(N) + admission control

- 14:45 CST 2026-11-01: base 7187b58 (step 24). Sandbox restarted again (no verilator, /tmp/omega_build lost): toolchain setup started (results/s25/setup.log).
- 14:55: toolchain ready; reg.sh started (results/s25/reg.status; resumable). No fabric.py / RTL / tb change planned (admission is a separate layer), so defaults stay identical by construction.
- 15:40: omega/symbolic.py (BM + exact closed forms, envelope fallback), omega/causal.py (W_nodes lib + W_vars), omega/admission.py (Scheduler), tests/test_s25.py written; quick sections green. Full test_s25 running (s25_full.log).
- 16:20: test_s25 mutants 6/6 caught (s25_mutants.log). Running sym_all.sh (symbolic.log, sort_decomp.log, wvars.log) then final full test_s25 (s25_full.log). reg: id 128/128, units 42, programs 315, s14 90 so far.
