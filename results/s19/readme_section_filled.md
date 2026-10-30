### Short retry timeout made safe: room-distance gradient, slot reserve and full-cell pass-on (step 19)

Step 18 left `+rto=8` as a knob: up to 58% faster under global memory pressure, but the fabric model
livelocked more often. Step 19 found why, fixed it, and makes the short timeout the default:
**`+rto=8 +rgrad=3`** (testbench defaults; `OMEGA_RTO` / `OMEGA_RGRAD` for the fabric model and
`omega/rtl.py`). **`+rto=32 +rgrad=0` is step 18 cycle for cycle** (all 24 runs of `results/s18/rto_global.jsonl`
at 32 reproduce exactly on the final RTL: `results/s19/rto_global_old.jsonl`, `rto_global_old2.jsonl`).

**Root cause 1: not a retry storm, but a global out-of-memory reached by ordering.** The livelock case is
global treesum(9) 3×3 (every cell but the far corner left with 8 free node / 8 free var slots). A stuck run
(`results/s19/diag.py`, `traj.py`, `bound.py`, `cq.py`, `exps.py`) ends with the corner's 1,024 var slots
full: 199 vars bound to tree constructors, 58 to unexpanded `gen` leaves, all other cells idle, only SPAWNs
circulating (300k of them), so nothing can ever be expanded again. One cell on its own needs 118 vars at the
peak (depth-first), so the program fits easily; what differs is the order. In a failing run the consumer
(`tsum`) expands 3–8 times in the first 3,000 cycles against ~76 producer (`gen`) expansions; in a
successful one 18–57 against 58–70 (`results/s19/ratio.py`). Parked producer SPAWNs (`gen__a2`, 6 nodes /
6 vars) escalate after 4 short parks and wander round robin into whichever ballast cell happens to fit them,
so the top of the tree is built in scattered poor cells; the consumer arms that must match it there
(`tsum__a3`, 5 / 5) find no room, and the matching consumer tasks end at the *bottom* of the corner's LIFO
stack while new producer work keeps arriving on top. The corner then materialises the whole tree and runs
out of vars. A shorter timeout makes the early wandering faster; rto = 32 hits the same race 2 times in 20.
The RTL reproduces it: global treesum(9) 3×3, seeds 1–30, `+rto=8` stops at ~2,900 of 18,410 interactions
10 times (status 3, cycle limit), `+rto=32` never (`results/s19/rtl_ts9.jsonl`).

**What did not work** (fabric model, treesum(9) 3×3 seeds 1–20 + the global set; `results/s19/fabric_table.md`,
`sweep1.jsonl`, `sweep2.txt`; patch of all probe knobs `results/s19/probe19_fabric_all_knobs.patch`):
per-cell exponential backoff of the retry timer (shift 1–3, reset on success or on any interaction) and
LFSR jitter on the reload: 7–16 livelocks of 20 instead of 19, and the backoff gives back the 8×8 gain
(treesum(7) 8×8 up to 26,190 fabric cycles); escalating later (`OMEGA_ESCN`, step 18): 7 / 20; aging the
LIFO (every k-th pop under pressure takes the oldest task, several gates): consumers run again but memory
grows breadth-first, 3–7 of 10 still livelock (`sweep2.txt`) and finishing runs are up to 50% slower. Retry timing is not the lever; *where* homeless
work goes is.

**The fix.** Each cell registers a 3-bit room distance `rdist` (0 when roomy, else 1 + the neighbours'
minimum, saturating at the run-time cap `rgrad`) and drives it to its neighbours next to `roomy`. Rules 1–3
apply when a neighbour is closer to room (*downhill*), rule 4 whenever `rgrad` ≠ 0:
1. a SPAWN that has no room and no roomy neighbour is forwarded downhill **at once** instead of being parked
   (so producer work goes to the room instead of wandering into poor cells; downhill only after one park:
   8 / 20 livelocks; only escalations downhill: 15 / 20);
2. escalated retries (SPAWN, SWI `NODE`, commutation `PULL`) go downhill instead of round robin;
3. an expansion must leave **4 free node and var slots** (`RSV19`). Root cause 2, found on the RTL once (1)
   was in: with only (1)–(2), global treesum(7) 8×8 stopped 4 times in 13 at `rgrad=3` (once in 3 at `rgrad=7`,
   at 4,565 of 4,586 interactions, few messages). The stuck mesh had a cell on the downhill path with 0 free
   node / 0 free var slots (`results/s19/diag_g7_ts7.txt`): SPAWNs passing through had been expanded there
   because they just fitted, and a cell with no free node cannot take the `NODE` / `PULL` at the head of its
   ejection port, so it blocks for good. The reserve keeps passing work moving downhill.
4. a `NODE` / `PULL` at the ejection head of a cell with **no free node slot at all and nothing else to
   do** is passed on to a roomy neighbour, else downhill, else round robin (a `NODE` whose partner is a
   node goes on as a `PULL`, so the taker asks for the partner and the full cell empties). Root cause 3:
   with (1)–(3), 30 seeds of global treesum(7) 8×8 still stopped twice (seeds 16 and 18, at 4,566 /
   4,551 of 4,586 interactions; `results/s19/rtl_ts7.jsonl`): a cell *more* than `rgrad` hops from the
   room (no downhill neighbour, so no reserve) had expanded to 0 / 0, and the `LINK`s that would have
   freed it were queued behind the blocked `NODE` (head-of-line; `results/s19/diag_rsv_ts7_s16.txt`).
   The same deadlock stops `+rto=8 +rgrad=0` on seed 9 (4,535 of 4,586), so it was there in step 18 at
   the short timeout. Passing the `NODE` on unchanged was not enough (it was migrated straight back by
   the redex rule: 207,337 `NODE` messages on seed 16, still stuck; log of that attempt not kept); as a `PULL` both seeds finish (7,528 / 6,206
   cycles, `results/s19/diag_fwd_ts7_s1*.txt`). Re-homing a node is not an interaction and is location
   free, so the rewrite keeps the result.

Without a downhill neighbour (room more than `rgrad` hops away, or the whole fabric full) rules 1–3 are the
step-10 rule and rule 4 only moves blocked arrivals on, so the overfull cases still end in status 3. All
four rules are off at `rgrad=0`. Cap 3 was chosen over 7 on both models: at 7
cells far from the room all funnel into one corner (RTL fib(12) 6×6 14,785 vs 12,888 cycles at `+rto=8`
alone; fabric fib(12) 6×6 +10%, treesum(7) 8×8 +58%); at 2 the fabric livelocks treesum(9) 3×3 8 / 20 again.

**Livelock rates** (runs that stop without progress; fabric: "no progress for 100,000 cycles", RTL: cycle limit):

| case (seeds) | model | `+rto=32 +rgrad=0` (step 18) | `+rto=8 +rgrad=0` | `+rto=8 +rgrad=3` (step 19) |
|---|---|---:|---:|---:|
| treesum(9) 3×3 (1–20) | fabric | 2/20 | **19/20** | **0/20** |
| list(20) 3×2 (1–20) | fabric | 0/20 | 0/20 | 0/20 |
| treesum(7) 8×8, fib(12) 6×6, qsort(15) 6×6, list(20) 3×2 (21–40 each) | fabric | 1/80 | 2/80 | 0/80 |
| treesum(9) 3×3 (1–30) | RTL | 0/30 | **10/30** | **0/30** |
| treesum(7) 8×8 (1–30) | RTL | 0/30 | 1/30 | 0/30 (rules 1–3 only: 2/30) |
| the other 7 global cases of the cycle table (1–13) | RTL | 0 | 0 | 0/91 |

Fabric: `results/s19/sweep5.jsonl`, `sweep6.jsonl`, `sweep7.jsonl` (final model), `fabric_table.md`; RTL:
`rtl_ts9.jsonl`, `rtl_ts9_fwd.jsonl`, `rtl_big.jsonl`, `rtl_ts7.jsonl`, `rtl_fwd.jsonl` (final RTL).

**Cycles under global memory pressure (RTL, seeds 1–13, treesum(7) 8×8 seeds 1–30, jitter 30%; mean of the runs that finished; every run checked against the semantic
reducer; `bench/rto18_rtl.py`, `results/s19/rtl_big.py`, table `results/s19/table19.py`):**

| case | `+rto=32 +rgrad=0` (step 18) | `+rto=8 +rgrad=0` | `+rto=8 +rgrad=3` (step 19) | Δ new vs 32 | Δ new vs 8/0 |
|---|---:|---:|---:|---:|---:|
| fib(12) 3x3 | 15,190 · 32 msgs [13] | 14,951 · 32 msgs [13] | 14,916 · 6 msgs [13] | -1.8% | -0.2% |
| treesum(6) 3x3 | 5,880 · 279 msgs [13] | 5,824 · 238 msgs [13] | 6,098 · 10 msgs [13] | +3.7% | +4.7% |
| list(20) 3x2 | 3,592 · 547 msgs [13] | 3,021 · 492 msgs [13] | 3,236 · 176 msgs [13] | -9.9% | +7.1% |
| qsort(15) 4x4 | 12,107 · 29 msgs [13] | 11,607 · 29 msgs [13] | 11,542 · 29 msgs [13] | -4.7% | -0.6% |
| sort(10) 3x3 | 4,113 · 27 msgs [13] | 3,828 · 27 msgs [13] | 3,761 · 21 msgs [13] | -8.6% | -1.7% |
| fib(12) 6x6 | 15,161 · 2,223 msgs [13] | 12,913 · 2,178 msgs [13] | 13,917 · 734 msgs [13] | -8.2% | +7.8% |
| qsort(15) 6x6 | 12,584 · 33 msgs [13] | 11,728 · 33 msgs [13] | 11,653 · 33 msgs [13] | -7.4% | -0.6% |
| treesum(7) 8x8 | 28,003 · 8,084 msgs [30] | 8,436 (**1/30 stuck**: seed 9) · 7,898 msgs [30] | 7,685 · 5,359 msgs [30] | -72.6% | -8.9% |

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

**No change without memory pressure.** With nothing parked and every cell roomy, `rdist` stays 0 and the
timeout is never loaded, so the default changes nothing: all 8 benchmark programs on 4×4 and 8×8, seeds 1–8,
reproduce `results/s15/final_*.jsonl` cycle for cycle with the same message counts (128/128 runs;
`results/s19/id_4x4.jsonl`, `id_8x8.jsonl`).

**Hardware cost.** 3 flip-flops per cell (`rdist`), 4 × 3 bits of neighbour wires, a 4-way 3-bit minimum,
four 3-bit comparators, a saturating increment, two adders on the room check and, for rule 4, one more
branch in the pick logic that re-addresses the ejection head into the outbox (a 2-bit kind rewrite and
two 4-bit coordinate muxes, reusing the existing roomy / downhill / round-robin selection): roughly
60–100 GE of logic per cell (estimate, not synthesised), under 0.1% of the step-8 cell's standard-cell logic; no memory. `rgrad` is a 3-bit run-time input
shared by all cells.
