   memory is detected (status 3 / "no progress"), never silently wrong.
4. **Low-memory watermarks (step 22, §5).** With `lm` = 2 the counterexample above finishes on 20 / 20 seeds
   (fabric model, corner 120–1024 free slots) and the RTL counterpart (corner 470–1024, 30 seeds, the RTL needs
   451–470 free slots for treesum(9) on one cell) on 30 / 30; finished runs take about the 1×1 time. This is
   the admission idea of (ii), not a guarantee: a program whose depth-first order on one cell needs more than
   any cell has, or memory spread thinner than `lm_hi` slots per cell, can still stop (detected, status 3).
