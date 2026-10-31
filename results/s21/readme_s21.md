### A default-configuration test for the full-cell pass-on (step 21)

Step 20's reserve 1 let the two seeds that caught mutant 50 (rule d, the full-cell pass-on, switched off) finish,
so its detector had to run them at `+rsv=4`. Step 21 looks for a case at the shipped default
(`+rto=8 +rgrad=3 +rsv=1`) where rule d is needed, and finds a simple one: **a home cell with no free node slot
at all.**

Search (fabric model, new diagnosis knob `OMEGA_PASSON=0` = mutant 50; `results/s21/sweep.py`, `sweep2.py`,
`sw2.jsonl`): ballast keeps of 4–12 free slots in every cell but the room (treesum(6), fib(12), list(20),
sort(10), qsort(15), treesum(7) on 3×3 / 4×4 / 3×2 / 4×3 / 8×8) never fire rule d at reserve 1 (0 pass-ons, the
mutant finishes cycle for cycle). Rule d fires only when a cell reaches *zero* free node slots, which reserve 1
now prevents wherever room is downhill. Keeps of 0–3 free node slots in (0,0) only, and in every cell but the
room:

| ballast (node / var slots left free) | runs | stuck with rule d | stuck without rule d |
|---|---:|---:|---:|
| 0 / 8, 0 / 30 in (0,0) (5 programs × 4 shapes × 3 seeds × 2) | 120 | 0 | **120** |
| 0 / 8, 0 / 30 in all cells but the room | 30 | 0 | **30** |
| 1–3 free node slots (1/1, 1/8, 1/30, 2/2, 2/8, 2/30, 3/3), (0,0) only | 420 | 0 | 1 |
| 1–3 free node slots, all cells but the room | 88 | 0 | 0 |

Why: the program's root lives in (0,0). The first `NODE` that migrates to its partner there waits at the
ejection head (no free node slot), the LINKs queued behind it cannot be taken, and the cell has nothing else to
do, so without rule d the run stops; with it the head is passed on (1–2 pass-ons per run) and everything finishes.

RTL (`results/s21/rtl_k0.py`, `rtl_k0.log`; the 10 ballast programs × shapes of `tests/test_mempress.py` at keep
0 / 8): correct design 10 / 10 finish with the right readback and interaction count; **mutant 50 stops on 10 / 10**
(status 3).

Adopted (tests only, no RTL or default change):
* `tests/test_mempress.py`: ballast keep **0 / 8** added (10 cases; mempress 44 → 54).
* Mutant 50's detector now runs at the default `+rsv=1`: ballast keep 0 / 8, fib(12) 2×2 and treesum(6) 3×2,
  both stop with the mutant. The 8×8 `+rsv=4` run is no longer needed (the mutant run gets ~25 min shorter: no 8×8
  build).
* Fabric knob `OMEGA_PASSON` (default 1) for the diagnosis.
