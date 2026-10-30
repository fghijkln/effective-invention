* **Decision: the default becomes `+rto=8 +rgrad=3`.** No run of the new default stopped (livelock column above:
  0 on both models, against 2 / 20 fabric and 0 RTL at `+rto=32`, and 19 / 20 fabric, 10 / 30 + 1 / 30 RTL at
  `+rto=8` alone), and it keeps or beats the short timeout's gain on 5 of 8 cases: treesum(7) 8×8 28,003 →
  7,685 cycles (−72.6%, 30 seeds; `+rto=8` alone 8,436 and one stuck seed), qsort(15) 4×4 / 6×6 −4.7% / −7.4%,
  sort(10) 3×3 −8.6%, fib(12) 3×3 −1.8%.
* **Where it gives something back.** list(20) 3×2 and fib(12) 6×6 keep about half of the `+rto=8` gain
  (−9.9% / −8.2% against `+rto=32`, +7.1% / +7.8% against `+rto=8` alone): homeless work now goes to the room
  instead of being spread round robin over the ballast cells. treesum(6) 3×3 is **3.7% slower than step 18**
  (6,098 vs 5,880): with the room 1–4 hops away, everything funnels to the corner. Known gap 3.
* **Fewer messages everywhere work moves**: treesum(6) 3×3 279 → 10, list(20) 3×2 547 → 176, fib(12) 6×6
  2,223 → 734, treesum(7) 8×8 8,084 → 5,359.
* `+rto=32 +rgrad=0` reproduces step 18 cycle for cycle on the final RTL as well (all 24 runs of
  `results/s18/rto_global.jsonl` at 32: `results/s19/rto_global_old2.jsonl`).
