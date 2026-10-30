# Step 20 status

Done (uncommitted until the regression finishes):
- A: diagnosis (diag.py, ftable.md): the room cell does all the work under step 19; reserve 4 -> 1 adopted
  (RTL input `rsv`, tb `+rsv` default 1, fabric OMEGA_RSV default 1; `+rsv=4` = step 19, verified on RTL t6/l20).
  Fabric probe knobs (default off): OMEGA_RSVI, OMEGA_RG1F, OMEGA_RG1D, OMEGA_RSVD, OMEGA_RG2.
- Mutant 51 (reserve without downhill neighbour) in rtl/omega_cell.sv + tests/mutants.py (kill: fib(10) 1x1 keep 45).
- B: SPEC §7.1 written; counterexample cex.py / cex.jsonl / cexdiag_k200_s1.txt / minkeep.txt.
- README: readme_section.md (template) -> fill.py -> readme_section_filled.md; known gap 3 + next step 3 edited.

Running / remaining (resume: `setsid nohup bash results/s20/reg.sh > results/s20/reg.log 2>&1 &` skips finished steps):
1. rtl3.sh: treesum(7) 8x8 seeds 1-30 at rsv=1 -> rtl1.jsonl (status in rtl3.status).
2. reg.sh: mut51, identity (id_*.jsonl, idcmp.txt), units, programs, s14, fuzz, bigfuzz, security, mempress, mutants -> reg.status.
3. Then: python3 results/s20/fill.py; insert readme_section_filled.md before the step-19 section in README.md;
   update the verification table header/counts (mutants 52), commits list; commit; push; check CI.
