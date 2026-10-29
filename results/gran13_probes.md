# Step 13: what a "granularity" signal can and cannot see (fabric model, 8×8, seed 1–2)

Probes: `bench/gran_probe.py`, `bench/overlap_probe.py`, `bench/experiments/fabric_step13_affinity.py`
(the fabric model with the two rejected adaptive schemes), sweeps `results/gs1.log` … `gs5.log`.
The fabric model is a task-level approximation (its 8×8 sum(1000) takes 56k cycles, the RTL 29k), so
it was used only to rank schemes; every decision was then measured on the RTL (`results/s13_*.jsonl`).

## 1. Per-definition statistics of SPAWNed work (static K = 4, K2 = 4)

Per received SPAWN: `run` = interactions the receiver does until it is hungry again; `nout` = NODE /
PULL messages it sends meanwhile.

| program | definition | spawns | run | nout |
|---|---|---:|---:|---:|
| sum(1000) | sum (strict linear recursion) | 499 | 0.0 | 1.00 |
| qsort(40) | rnd (list generator) | 21 | 0.0 | 1.05 |
| qsort(40) | Cons (constructor) | 46 | 0.0 | 1.04 |
| qsort(40) | lo / hi arms | 9–58 | 1.2–6.8 | 1.1–1.6 |
| qsort(40) | qs__a5 (fork arm) | 39 | 15.2 | 2.95 |
| list(120) | range (generator) | 60 | 0.0 | 1.05 |
| list(120) | map__a2 | 4 | 6.0 | 1.00 |

Almost every spawned job does ~0 interactions where it lands: the expanded root meets its partner,
which lives at the sender, so the root migrates straight back (nout ≈ 1). The `sum` job and the `rnd`
or `range` job look identical at the receiver (run 0, one NODE back, same free-slot residue ≈ 10),
yet giving `rnd` makes qsort faster *and* cheaper while giving `sum` only adds a hop to sum's critical
path. What differs is what happens *later*: rnd's Cons cells stay spread over the mesh and the
filters migrate to them in parallel; sum's pending `+` nodes are consumed in strict order.

## 2. Rejected adaptive schemes

| scheme | idea | result (fabric, qsort / list / sum 8×8) |
|---|---|---|
| A. run-length counters | per-cell 2-bit counter per definition, up when a received job runs ≥ G interactions, down otherwise; ≥ 2 relaxes K to 4, 0 tightens to 32 | positive feedback: once relaxed, a strict chain stays longer at each receiver, so sum learns "coarse" (sum 56.2k → 63.0k cycles, msgs/int 0.05 → 0.27); tightening constructors (run 0) slows qsort 22.1k → 30.6k |
| B. data-affinity counters | tag nodes created by a received job with its definition; a consumer that migrates in and meets such a node = credit, the node migrating away = debit; the receiver's verdict is used for the give | neutral init (1): almost nothing is sampled (qsort 22.1k → 21.8k); optimistic init (2): helps qsort (17.2k) and list (14.1k) but every fresh cell on a chain's path starts optimistic, so sum is relaxed too (60.9k, 0.26 msgs/int) |
| C. local message-budget governor alone | per cell: relax / tighten the producer threshold by the messages it sent per interaction in an epoch of 32 interactions | regulates qsort (B = 50: 18.2k, 0.50) but not list (0.60 at every budget: its messages come from constructor spawns the governor does not control) |

Ablation (fabric, mean of 3 seeds, threshold 4 for one group only, everything else step 12):

| relaxed group | qsort(40) 8×8 cycles | msgs/int |
|---|---:|---:|
| none (step 12) | 22,510 | 0.433 |
| rnd (generator) | 19,394 | 0.413 |
| lo + hi (filters) | 19,045 | 0.545 |
| lo/hi arms only | 20,214 | 0.507 |
| lo/hi entries only | 23,235 | 0.522 |
| app | 22,799 | 0.431 |

## 3. What was kept

The useful split is not fine vs coarse but **producer vs strict** linear recursion, and it is a
property of the call graph: a recursion SCC whose templates call a constructor (or another
non-recursive definition) emits a data structure piece by piece; one that only calls itself and
operators is strict. The loader marks producers in directory bit 58 (`fabric.fork_defs(..., with_prod=True)`),
the cell gives them with their own threshold `spawn_kp`, and an optional per-cell message-budget
governor (scheme C) can move that threshold at run time. Strict recursions keep `spawn_k` = 16.
