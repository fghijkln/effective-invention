### Where the step-19 default gives cycles back, and what progress it guarantees (step 20)

Step 19 left two loose ends: under global memory pressure its default (`+rto=8 +rgrad=3`) is 3.7% slower than
step 18 on treesum(6) 3×3 and gives back about half of the `+rto=8` gain on list(20) 3×2 and fib(12) 6×6;
and it had no argument for *why* it should not livelock. Step 20 finds the cause of the first, keeps the one
cheap fix that is safe (**slot reserve 4 → 1**, new run-time input `+rsv` / `OMEGA_RSV`, `+rsv=4` = step 19
cycle for cycle), and writes the progress argument down with a counterexample (SPEC §7.1).

**A. Cause: the ballast cells stop working.** Under the step-19 rules every homeless task near the room goes to
the room, so the one roomy cell does almost all of the work. treesum(6) 3×3 seed 1 on the fabric model
(`results/s20/diag.py`): the room cell does 2,040 of 2,270 interactions at `+rto=32`, 2,081 at `+rto=8` alone,
and **all 2,270** at the step-19 default; list(20) 3×2: 918 / 849 / 1,037 of ~1,070; fib(12) 6×6: every cell
within 3 hops of the room does 0 interactions under the default and 9–60 each before. The run time is the room
cell's work, so moving ~10% of it back to the 8-free-slot ballast cells is the whole difference. The corner
never gets near its watermark in these runs (it uses at most 244 of 1,024 var slots), so `roomy` never changes
and hysteresis on it cannot matter here.

Which rule takes the work away (fabric model, 20 seeds each, mean cycles; treesum(9) 3×3 = the step-19
livelock set; `results/s20/ftable.md`, `sw1.jsonl`, `sw2.jsonl`, `sw4.jsonl`, `sw6.jsonl`; `perf.py`; knobs below are
fabric-only probes, all off by default):

{FTABLE}

* The **reserve** (rule 3) is most of it on list(20) and fib(12): with 8 free slots a ballast cell cannot
  expand a 5–6-node definition if it must leave 4 free, so every such SPAWN is sent on. Reserve 1 or 0 gives
  back list(20) 6,943 → 6,166 / 5,984 and fib(12) 6×6 33,706 → 33,102 / 33,042, with 0 livelocks.
* Turning off **downhill-at-once** (rule 1, `rgm0` / only after a park `rgm2` / only when nothing fits
  `rg1f1`) or the **downhill escalation** (rule 2, `rg2off`) alone does not help: the parked SPAWN then
  escalates downhill anyway, or the reserve still sends it on.
* treesum(6) needs **all three** off to get back to `+rto=8` (seed 1: 12,952 vs 13,566 with rules 2+4 only), and
  that configuration is step 18's round-robin spreading again: it livelocks treesum(9) 3×3 {R0OFF}
  (`rsv0rgm0rg2off`), and reserve 0 with rule 1 off already does 15 / 20. The spreading that helps
  treesum(6) is the same mechanism that builds treesum(9)'s tree in scattered poor cells (step 19, root cause 1);
  the two cases differ only in how much memory the program needs, which no cell can see locally.
* Rejected: waiving the reserve in an idle cell (`rsvi1`: 2 / 20 livelocks), the reserve only far from the room
  (`rsvd2`: little gain), rule 1 only far from the room (`rg1d2`: no change; near the room the roomy neighbour
  is taken first anyway). "Engage the gradient only when local free < threshold" cannot separate these cases:
  every ballast cell has exactly 8 free slots, so any threshold is either "always" or "never".

**Adopted: reserve 1.** With room downhill an expansion still never takes a cell's *last* node or var slot, so a
`NODE` / `PULL` passing through can always be absorbed (the deadlock the reserve was added for, step 19 root
cause 2), but a ballast cell can run one small expansion again.

Livelock sets at the new default (`+rto=8 +rgrad=3 +rsv=1`):

| case (seeds) | model | step 19 (`+rsv=4`) | step 20 (`+rsv=1`) |
|---|---|---:|---:|
| treesum(9) 3×3 (1–20) | fabric | 0/20 | 0/20 |
| treesum(7) 8×8, fib(12) 6×6, qsort(15) 6×6, list(20) 3×2 (21–40 each) | fabric | 0/80 | 0/80 |
| fib(12) 3×3, qsort(15) 4×4, sort(10) 3×3 (1–20 each) | fabric | 0/60 | 0/60 |
| treesum(9) 3×3 (1–30) | RTL | 0/30 | 0/30 (`results/s20/rtl_ts9.jsonl`) |
| treesum(7) 8×8 (1–30) | RTL | 0/30 | {T7LL} |
| the other 7 global cases (1–13) | RTL | 0/91 | {OTHLL} |

Cycles under global memory pressure (RTL, same runs as the step-19 table: seeds 1–13, treesum(7) 8×8 seeds 1–30,
jitter 30%, every run checked against the semantic reducer; `results/s20/rtl1.jsonl`, `rtl_big.py`, `summ.py`):

{RTABLE}

* `+rsv=4` reproduces step 19 exactly on the RTL (treesum(6) 3×3 6,098 and list(20) 3×2 3,236, 13 seeds each).
* Gains: list(20) 3×2 −3.8% and fib(12) 6×6 −1.6% against step 19 (now −13.3% / −9.7% against step 18,
  +3.1% / +6.0% against `+rto=8` alone, which livelocks); the rest within ±0.2%. Messages rise a little where
  work spreads again (treesum(6) 10 → 56, list(20) 176 → 240, fib(12) 6×6 734 → 880), still far under step 18
  (279 / 547 / 2,223).
* **treesum(6) 3×3 stays 3.7% slower than step 18** (6,100 vs 5,880): on the RTL the reserve was not what kept
  the work away, rules 1–2 are, and turning those off brings back the treesum(9) livelock. Kept as known gap 3.
* Without memory pressure nothing changes (the reserve only applies with a downhill neighbour, i.e. with a
  non-roomy cell): {IDLINE}

**B. Progress: what the default guarantees and what it cannot** (full text SPEC §7.1).
1. *Safety* holds unconditionally: re-homing work is location free, so a run that ends has the semantic result.
2. *The network cannot deadlock* as long as some cell has a free node slot for each `NODE` / `PULL` it must take:
   XY routing is deadlock free when ejection drains, the head of an ejection port can only block on a
   `NODE` / `PULL` in a cell with no free node slot, every task of such a cell completes or leaves it in bounded
   time (sends never block, homeless work parks for `rto` cycles and leaves after 4 parks), and once the cell has
   nothing else to do rule 4 passes the head on. With room downhill the reserve keeps a cell from reaching that
   state through expansions at all.
3. *Placement is live within the gradient*: while a cell stays roomy, a SPAWN that does not fit within `rgrad`
   hops of it moves to a strictly smaller room distance on every failure and reaches a roomy neighbour in at most
   `rgrad` hops. Farther away it moves round robin (a rotor-router walk, which for a single walker visits every
   cell within O(|E|·D) moves; with the rotors shared by other traffic this is an argument, not a proof).
4. **No completion guarantee, and no cheap local mechanism can give one.** Counterexample
   (`results/s20/cex.py`, `cex.jsonl`, `cexdiag.py`): treesum(9) on one cell needs **115** free node / var slots
   (depth first; `minkeep.py`). On 3×3 with 8 free slots in each ballast cell and **200** in the corner (264 in
   total, 2.3× the sequential need) the default stops on **20 / 20 seeds** (so does `+rto=32 +rgrad=0`); with 300 in
   the corner all 20 finish. The stopped state (seed 1: 791 of 18,410 interactions): every pending task is a
   SPAWN (5 queued, 9 parked), no cell has more than 4 free var slots, the corner has 97 free nodes but 2 free
   vars. The parallel order has materialised more than twice the sequential peak, and what is left is
   fragmented below the size of any definition, so **no schedule can continue**: neither a hop budget nor an
   escape network helps, because there is no place to put the work. (At 200 free slots the corner is also below
   the absolute `roomy` watermark of 256, so the gradient never sees it; a lower watermark, 64 / 32, still stops
   5 of 10 seeds.) A real guarantee needs memory-aware admission before the fabric fills (e.g. a global
   low-memory mode that stops giving work away and runs depth first) or spilling to off-fabric memory; both are
   bigger than a step and are listed under next steps. A hop budget would only turn endless bouncing into a quiet
   out-of-memory stop, which status 3 already reports.

**Hardware cost.** None new: `RSV19` becomes the 3-bit run-time input `rsv` shared by all cells (the adders on
the room check already existed). Mutant 51 (reserve applied without a downhill neighbour) is caught by fib(10)
on 1×1 with exactly the 93 free slots its RTL run needs (`results/s20/minkeep_rtl.py`).
