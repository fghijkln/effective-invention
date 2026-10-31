* **Low-memory watermarks (step 22).** Run-time inputs `lm_mode` (2 bits), `lm_hi`, `lm_lo` (8 bits),
  `lm_rsv` (5 bits) (`+lm` / `OMEGA_LM`, `+lmhi`, `+lmlo`, `+lmrsv`; defaults 2, 64, 32, 16). In low-memory
  mode `roomy` is set at ≥ `lm_hi` free node and var slots and cleared below `lm_lo` (absolute, instead of
  SLOTS/4 / SLOTS/8), and rule (c) above keeps `lm_rsv` slots instead of `rsv`. `lm_mode` = 0: never (step 21
  cycle for cycle); 1: while no cell is *ample* (≥ SLOTS/2 free node and var slots, cleared below SLOTS/4; each
  cell drives one `ample` bit, the mesh ORs them in a registered tree like the quiescence tree and returns
  `lowmem`); 2 (default): always. Without pressure every cell stays above `lm_hi`, so `rdist` stays 0 and
  nothing changes (the identity check is cycle-identical); under pressure a corner with a few hundred free slots
  is room, the gradient points at it, and poor cells stop starting definitions of their own, so work collects
  where the room is and runs depth first there (§7.1). Mutant 52 (the mode never engages).
