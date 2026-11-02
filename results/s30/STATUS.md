# Step 30 status: task stack + joint node/var loads in the certificate
- 17:32 CST 2026-11-02: start (main c2eb892). Sandbox restarted; toolchain rebuilt (results/s30/tc.log).
- 18:20: finding: with RTL-sound loads the joint hull of (live nodes, live vars) over causally closed prefixes is
  exactly the box [0, W_nodes] x [0, B_vars] for fib / treesum_direct / sum / fact (one closed set attains both), and a
  few % below it for list / higher / treesum / sort. The floor-sum cover is already exact for a box, so the gain comes
  from W_nodes (causal) replacing B_nodes plus the hull: 1.26-1.55x smaller cells, not 2x (vars stay at B_vars:
  RTL var frees are not tied to an event). omega/joint.py, results/s30/{seqs,cert_table,direct}.py.
- Task stack: linear-reference bound, entries (all cells) <= n + 2v + A (A = atom-atom interactions); Q = max(n+2v)+A+1;
  certificate requires QDEPTH >= Q + 2WH + 3. RTL +tcert audit (sim only) + joint-hull peaks (jcert_peak_*).
- treesum_direct(14) now certified on 2x2 x 53,315 (step 29: 73,789); fib(20) 2x2 needs 77,487 (no).
- RTL validation lanes: small+hetero (ob1), boundary+big (ob2). Boundary: QDEPTH below need -> status 2; 3x3 with 10 free
  slots per cell (no roomy cell) -> treesum(4) stalls (status 3). treesum_direct(14) 2x2 x 53,315 runs sound.
- tests/test_s30.py --ci 1850/1850.
- 20:20: executor crashed; 20:35 resumed (wip 38eba1f + a7db455 already on origin/main). Sandbox had restarted
  (toolchain rebuilt, results/s30/tc2.log). Done before crash: val_small 128/128, val_hetero 43/43 certified sound
  (21 uncertified finished), val_boundary 37 (all uncertified: QDEPTH-below-need -> status 2 in 8/10, frag10 treesum(4) ->
  status 3), val_big 118/118 sound, s30 checker mutants 8/8 (mut.log), id4 64 runs. Lanes relaunched: lane1.sh (val_big
  rest, then test_s30 full), lane2.sh (id8, idcmp, units, programs, s14). Regression reuse: since c2eb892 the RTL change
  is an extra audit output port + a +tcert-gated sim block; Python change is a new module only (omega/joint.py), so the
  step-29 results for fuzz/bigfuzz/security/mempress/mutants 55/Ω-L/s25-s29 carry over (identity re-checked cycle-for-cycle).
- 21:15: val_big 138/138 sound (all 138 big jobs done) -> 309/309 certified RTL runs sound in all; test_s30 full 1856/1856
  (280 s); validation.md (results/s30/report.py) with smallest-cell and certifiable-N tables vs step 29. wip 3 d3f5de7
  (CI 41452499442 success), wip 4 d7c8079 (README totals).
- 21:55 rerun on step-30 code at defaults: identity 128/128 (id4 64 + id8 64 cycle-identical to step 15), units 42/42,
  programs 315/315, s14 90/90, fuzz 600/600, mempress 60/60, test_s29 326/326. Sandbox restarted again ~21:56 (toolchain
  rebuilt, tc3.log); security + bigfuzz relaunched (lane5/lane6). Carried over from step 29 (c2eb892, same default RTL
  behaviour): RTL mutants 55/55, Ω-L 597/597 + 7/7, s25 2749/2749 + 6/6, s26 76/76 + 5/5, s27 253/253, s28 129/129 + 2/2,
  s29 mutants 8/8.
resumed 2026-11-02 22:32 CST (executor 3)
