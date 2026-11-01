# TACHYON-Ω — Spatial Interaction-Net Fabric: specification (MVP)

TACHYON-Ω is a processor with **no CPU/memory split, no program counter, no shared address space and
no instruction stream**. The machine is a W×H mesh of identical *active memory cells*. Each cell stores
part of a program's graph (an interaction net) and rewrites the parts it stores. Whatever the cell holds
decides what it does next: a cell with no active pair (redex) and no incoming message does nothing. A
program is a graph, running it is local graph rewriting, and the result is the normal-form graph left
in the cells' RAMs.

Files: golden models `omega/semantic.py` (any-order reducer) and `omega/fabric.py` (cycle-level fabric
model and loader); RTL `rtl/omega_{pkg,router,cell,mesh}.sv`; frontend `omega/lang.py`; text IR
`omega/ir.py`.

---------------------------------------------------------------------------------------------------

## 1. Computation model

Lafont interaction combinators (CON, DUP, ERA) with HVM2-style numeric extensions and global
definitions, following HVM2 (Taelin, *HVM2: A Parallel Evaluator for Interaction Combinators*) and the
lazy-reference discipline used by Bend. The Δ-Nets paper (arXiv 2505.20314) motivated using labelled
duplicators and keeping the rule set small and local. TACHYON-Ω does not implement Δ-Nets' optimal
reduction (§11).

| node | arity (aux ports) | meaning |
|---|---|---|
| `ERA` `*` | 0 | eraser |
| `NUM` `#n` | 0 | 32-bit unsigned number atom |
| `REF` `@f` | 0 | reference to global definition *f*. It expands lazily, only when it meets a node that needs it |
| `CON` `(a b)` | 2 | constructor: λ-abstraction, application, pair, Scott-encoded data |
| `DUP` `{L a b}` | 2 | duplicator with a 16-bit label L |
| `OPR` `$(op a r)` / `$(op' a r)` | 2 | binary operator. Principal = incoming operand, `a` = the other operand, `r` = result. The flip bit `s` (`'`) records whether the incoming operand is the left (s=0) or right (s=1) one |
| `SWI` `?(a r)` | 2 | switch on 0 / non-zero. Principal = number, `a` = `(zero_case succ_case)`, `r` = result |

The 16 operators are `+ - * / % == != < > <= >= & | ^ << >>`. All are 32-bit wrapping; `/` and `%` by
0 give 0, and shifts use the low 5 bits.

**Wires and variables.** As in HVM2, a node stores only its two *aux* ports. Its principal port is
implicit: whoever holds a pointer to the node (a port with a node tag and the node's address) is
connected to its principal. A wire between two aux ports is a **var**, a one-word cell holding a
*substitution*. Both ends hold `VAR(v)`, and `var[v] = NONE` until one end is linked to something.
Node slots are written only when a node is created and never mutated afterwards. Every concurrent
update goes through var exchanges, so there are no back-pointers to keep consistent.

### Why the principal port is implicit (deviation from the brief's "3 port pointers" node)
The brief suggested `type + label + 3 port pointers` per node. With explicit bidirectional pointers,
a rewrite must update the far end of every wire it touches. When two neighbouring redexes are rewritten
at the same time in different cells, both try to re-point the same wire end. That race is exactly what
HVM2's var-substitution `link` exists to remove. TACHYON-Ω keeps the 128-bit slot and the
`(cell_x, cell_y, slot)` port pointers, but stores two aux ports per node, takes the type and label from
the pointer, and lets the cell that owns a var serialise every exchange on it. Single-owner
serialisation is what turns HVM2's atomic swap into a plain local read-modify-write.

## 2. Encodings

### 2.1 Port (64 bit)
```
[63:60] tag     0 NONE  1 VAR  2 REF  3 ERA  4 NUM  5 CON  6 DUP  7 OPR  8 SWI
[59:44] label   DUP label | OPR {s[4], op[3:0]} | REF definition id
[43:40] owner   owner capability id of the tenant the port belongs to (0..14; §12)
[39]    ABS     template-only flag: absolute (forged) pointer, not relocated on expansion (§12)
[38:32] 0
[31:0]  payload NUM: value.  VAR / node tags: address {x[23:20], y[19:16], slot[11:0]}
```
Up to 16×16 cells and 4096 slots per cell. The RTL default is SLOTS = 1024.

### 2.2 Node slot (128 bit) and shadow tag
`node_mem[slot] = {aux2[127:64], aux1[63:0]}`. One shadow tag bit per slot, `nalloc`, marks a live
node. The loader sets it, `alloc` sets it and `free` clears it. Node counts and the dump readback
are taken from it.

### 2.3 Var slot (64 bit)
`var_mem[slot]` holds a substitution port, or 0 (NONE). Invariant: a free var slot always holds NONE,
so allocation needs no initialisation write.

### 2.4 Definition ROM (read-only templates; one per cluster of cells since step 7, §5.3)
`dir[id]` points to a header entry `{counts, root}` with
`counts = nn[7:0] | nv[15:8] | nr[23:16]`. The header is followed by `nn` node entries `{aux2, aux1}`
and `nr` redex entries `{b, a}`. Template ports carry local indices in their payload: `VAR i` means
fresh var *i*, and `CON j` etc. mean fresh node *j*. The ROM is a table of graph templates, comparable
to a microcode/constant ROM. It is never fetched sequentially and holds no control flow.
The per-cell directory word also carries the loader's spawn hints (§5): bit 56 fork, bit 57 rec,
bit 58 prod (step 13).

### 2.5 Text IR (HVM2 style)
```
@fib  = ({1 v1 v2} v5) & v2 ~ $(< #2 v3) & v3 ~ ?((@fib__a1 @fib__a2) v4) & v4 ~ (v1 v5)
@main = r & @fib ~ (#20 r)
```
Each variable name occurs exactly twice per definition. `& a ~ b` lists the definition's initial links
and redexes.

## 3. Rule table

`link(a, b)` is the only way two ports get connected:
```
link(a, b):
  loop:
    if a is not VAR and b is VAR: swap
    if a is not VAR:            redex(a, b); return        -- two principals met
    old = var[a]; var[a] = b    (atomic at a's home cell)
    if old == NONE: return                                  -- other end will find b
    free var a; a = old                                     -- both ends known: keep joining
```
**Local-first orientation (step 12).** When both sides are vars, `link` is symmetric: the exchange may
happen at either var's home cell. A cell therefore swaps the pair when `a` is a remote var and `b` a
local, in-bounds var (`lflip` in `omega_cell.sv`, `Cell.flip` in the fabric model; configuration bit
`link_local`, default on). The exchange then happens here, with no LINK message: `b` either takes `a`
(and the message, if any, is sent later by whoever reaches `b` second) or `b` was already substituted
and the loop continues with `old ~ a`. Atomicity is unchanged (every exchange is still at the var's own
cell), and all owner checks are symmetric or run on whichever var becomes `a`. On 8×8 it removes
25-55% of the LINK messages of the low-parallel programs and treesum (results/bench_msgs.md).
For `redex(a, b)` the pair is first oriented so that `P` has the larger `(tag, label)` and `Q` the
smaller. The rules are total, with exactly one rule per pair, so strong confluence holds: every
schedule performs the same multiset of interactions and reaches the same normal form.

| pair | rule | interactions |
|---|---|---|
| ERA/NUM ~ ERA/NUM, REF ~ ERA | void | 1 |
| REF `@f` ~ NUM or REF | expand *f* (for REF~REF the smaller id) and link its root with the other atom | 1 |
| REF `@f` ~ CON/OPR/SWI | expand *f* and link its root with the node. The node is *not* consumed | 1 |
| REF ~ DUP{a1 a2} | copy: `link(a1, @f)`, `link(a2, @f)` | 1 |
| ERA ~ node{a1 a2} | `link(a1, *)`, `link(a2, *)` | 1 |
| NUM ~ CON/DUP{a1 a2} | copy: `link(a1, #n)`, `link(a2, #n)` | 1 |
| `#x` ~ OPR(op,s){a1 a2} | if `a1` is an immediate `#y`: `link(a2, #(s ? y op x : x op y))`; else make `OPR(op, ¬s){#x a2}` (reusing the slot) and link `a1` with it | 1 |
| `#0` ~ SWI{a1 a2} | `link(a1, (a2 *))` (slot reused) | 1 |
| `#n+1` ~ SWI{a1 a2} | `link(a1, (* (#n a2)))` (one slot reused, one new) | 1 |
| CON~CON, DUP{L}~DUP{L} | annihilate: `link(a1,b1)`, `link(a2,b2)` | 1 |
| any other node pair (CON~DUP, DUP{L}~DUP{M≠L}, OPR/SWI with anything) | commute: 2 copies of each, 4 fresh vars, 2 slots reused, 2 new | 1 |

The OPR rule looks only at what is *stored* in `a1`. Stored contents are fixed when the node is
created, so they do not depend on the schedule, and the interaction count stays invariant.
Interaction count, live node count and canonical root readback are the three observables that every
model and the RTL are checked on.

## 4. Message protocol

All inter-cell communication is a single wide flit
`{kind[1:0], dx[3:0], dy[3:0], p3, p2, p1, p0}` (266 bits):

| kind | payload | sent when | receiver does |
|---|---|---|---|
| `LINK` | p0 = a, p1 = b | a link whose var (or principal node) lives elsewhere | runs `link(a, b)` locally. The destination is the cell owning the var, or the node for a redex being forwarded |
| `NODE` | p0 = node pointer (tag, label), p1/p2 = its aux ports, p3 = partner pointer | a binary-binary redex whose nodes are in two cells: the local node **migrates** to its partner's cell | allocates a slot, writes the node there (*re-homing*) and runs `link(new, partner)`. Both nodes are now local |
| `SPAWN` | p0 = REF id, p1 = partner port | a REF expansion given to a *hungry* neighbour (work distribution), or forwarded because the cell is out of slots | expands the definition locally and links its root with the partner (which may stay remote) |
| `PULL` | as `NODE` (p0 = node P, p1/p2 = its aux ports, p3 = partner Q, a node in the sender) | a local commutation P ~ Q for which the cell has no free slots (memory pressure, §5): sent to a *roomy* neighbour | re-homes P (P'), then sends `LINK(Q ~ P')` to Q's cell (task kind `K_FWD` if the outbox is full). There the ordinary NODE rule migrates Q to P', so both nodes end up in the roomy cell, which applies the rule |

**Remote-pointer path compression (step 12 study, not implemented).** A LINK that reaches a var
already substituted by a var in a third cell is forwarded there. Compressing the path ("update the
source pointer to the final owner") has nothing to update in a linear net: the pointer that caused
the LINK was consumed by it, and the intermediate var is freed by the forward, so no copy of either
remains. Only a chain of two or more forwards could be shortened at all, and `bench/link_forwards.py`
measures that bound on 8×8 with the step-11/12 policy: 176 of 3,489 LINKs for qsort(40), 1 of 1,195
for list(120), 208 of 3,880 for treesum(9) (≤ 5.4%). Local-first orientation (above) is the change that
cuts forwarding itself (qsort forwards 1,483 → 839). Same-cycle merging of two LINKs to one
destination into one flit was also measured: the outbox drains every cycle, so the fabric model found
no LINK ever queued behind another LINK to the same cell (0 opportunities in qsort, list, treesum,
fib on 8×8); not implemented.

Correctness argument (also checked by fuzzing):
1. A var has exactly two occurrences, and each occurrence is consumed by at most one `link`. All
   exchanges on a var happen at its home cell, one at a time, so the HVM2 lock-free link argument
   applies with "atomic swap" replaced by "the owner cell's single-ported read-modify-write".
2. A node's principal pointer exists in exactly one place: an aux slot, a var, a task, or a message.
   When it takes part in a redex, the pointer is in the redex and nowhere else. Migrating or freeing
   the node therefore never leaves a dangling pointer, and its aux ports keep their var occurrences
   unchanged.
3. Messages may be delayed or reordered arbitrarily. Every operation is a link/redex on ports whose
   ownership is exclusive, so the order only changes which cell performs the final join, never the
   result.

## 5. Cell microarchitecture (`rtl/omega_cell.sv`)

```
            +--------------------------------------------------------------+
  N/E/S/W   |  router: 4 input FIFOs (depth 4) + outbox + eject FIFO         |
 <=======>  |  XY routing, LFSR arbitration, optional link jitter           |
            +------------+---------------------------------^---------------+
                         | eject                           | outbox (depth 4)
            +------------v---------------------------------+---------------+
            | rewrite engine (FSM):                                          |
            |   IDLE -> LINK <-> PUSH, SPAWN, EXPH -> EXPN -> EXPR -> LINK   |
            |   rule logic + 32-bit ALU                                      |
            +---+-----------+--------------+---------------+---------------+
                |           |              |               |
          node RAM      var RAM       free stacks      task stack (LIFO, 1024 x 130 b)
          1024x128b     1024x64b      node / var       directory; def ROM per cluster (5.3)
          + nalloc tag
```
* **Local allocation.** A rewrite allocates in its own cell from the free stacks. Commutation and SWI
  reuse the consumed slots. A full cell never borrows a slot remotely. Instead it (a) migrates its node
  to the partner (NODE) or (b) forwards a SPAWN to a neighbour, so the work moves to free memory
  rather than memory being lent to the work.
* **Spawn policy (demand-driven).** Each cell drives a 1-bit `hungry` wire to its four neighbours:
  engine idle, task stack empty, nothing ejected. When a REF meets a node, the engine hands the
  expansion to the first hungry neighbour, scanning N, E, S, W from a rotating start. If no neighbour
  is hungry it expands locally. This is the only load-balancing mechanism. It uses neighbour-local
  wires only, with no global information. An earlier round-robin *push* policy (v0, commit fc3d68d)
  sent ~100× more messages and could exhaust a 2×2 fabric's memory, because eager breadth-first
  unfolding filled the cells. The pull-like policy keeps every cell depth-first until a neighbour asks
  for work.
* **Sender-side spawn threshold and definition hints (step 11).** A hungry neighbour alone does not
  get the REF any more. The loader marks two bits in every directory word (`fabric.fork_defs`):
  bit 56 **fork** — the definition belongs to a recursion SCC that some template calls at least twice
  (both halves of a divide-and-conquer recursion: fib, gen/tsum, qs; the two arms of a switch count
  once); bit 57 **rec** — the definition belongs to any recursion SCC (list walks, filters, counters
  as well). With `spawn_hint` set (default) the sender hands the REF to a hungry neighbour only if
  * it is a fork target (always: coarse-grained work), or
  * it is a linear-recursion definition and more than `spawn_k` tasks wait on the local task stack
    (default 16), or
  * it is non-recursive (constructor, arm, `main`) and more than `spawn_k2` tasks wait (default 4).
  Without the hint every REF uses `spawn_k`; 255 means no threshold (spawn_k = 255, hint off is the
  step-10 policy). All three are configuration inputs of the mesh (`+spawnk`, `+spawnhint`,
  `+spawnk2`), so one build serves every setting. Otherwise a sequential chain hopped from cell to
  cell dragging its wires behind it (each hop cost about 8 LINK + 3 NODE messages in qsort). The
  decision is made in S_LINK from the read-ahead directory word and `tq_tot`, with no extra cycle.
  Sweeps (`results/spawn_sweep.md`): a threshold alone was rejected (K = 2 slows fib(20) 4×4 by 36%,
  K = 8 by 3.1×); spawn_k sets the trade-off for linear recursions (sum(1000) 8×8 is slower than one
  cell below K ≈ 12), spawn_k2 the one for constructors (treesum(9) 8×8, mean of 4 seeds: 2,178
  cycles with K2 = no threshold, 2,374 with 4, 2,646 with 2; qsort/list exceed 0.5 msgs/interaction
  with no threshold).
* **Producer recursions and the message-budget governor (step 13).** Measuring the granularity of
  handed-out work per definition does not separate the cases that matter (`results/gran13_probes.md`):
  a spawned job almost never runs where it lands (its root meets a partner that lives at the sender
  and migrates straight back), and the job of a strict counter (`sum`) and that of a list generator
  (`rnd`, `range`) look the same at the receiver. Two adaptive schemes built on such counters were
  rejected (run length: positive feedback relaxes the strict chain; data affinity: unsampled cells
  start optimistic). What separates them is the call graph: the loader marks bit 58 **prod** on every
  linear recursion (rec, not fork) whose SCC calls a non-recursive definition outside the SCC (a
  constructor or a lifted arm), i.e. a recursion that emits a data structure piece by piece (rnd, lo,
  hi, app, range, map, insert). Its consumer can work on the head while the tail is being made, and
  the pieces stay spread over the cells that made them. Strict recursions (sum, fact, check, lsum,
  foldr into an operator) only feed their own pending operators. A producer REF is given while more
  than `kp_eff` tasks wait; strict recursions keep `spawn_k`, non-recursive definitions `spawn_k2`.
  `kp_eff` = `spawn_kp` (`+spawnkp`, default 4, 255 = always) unless the per-cell **message-budget
  governor** is on (`+govb` = budget B in messages per 100 interactions, 0 = off, default off): a
  3-bit level (reset 2) selects `kp_eff` = 0 / 2 / 4 / 8 / 16; after every epoch of 32 interactions the
  cell compares the messages it sent in the epoch (saturating 8-bit count) with B: more than B per 100
  interactions moves the level up (tighter), less than half moves it down. Cost: 6 + 8 + 3 flip-flops,
  a 32-bit copy of the interaction counter and two constant multiplies per cell; the decision stays in
  S_LINK. Fork and non-recursive definitions are untouched, so fib and both tree sums run exactly as in
  step 12.
* **Fork deque and oldest-fork give (step 14).** A pure LIFO stack hands a hungry neighbour the *newest*
  (small, deep) fork task; the big shallow subtrees sit at the bottom of a few busy cells and run
  serially, which made the tail of fork programs on 8×8 long and seed-dependent (fabric study
  `results/var/REPORT.md`). Each cell gets a 4-entry **fork deque** beside the task stack. A pushed task
  is a *fork task* when it is a ready `REF ~ x` redex (`x` a NUM / OPR / CON / SWI of the same owner, no
  var, REF, ERA or DUP) whose REF names a fork definition; it goes on the deque while the deque has room,
  everything else (and a fork task finding the deque full) on the stack, in push order. Classification
  needs no directory read: a per-cell flip-flop vector holds one hint bit per definition, written
  together with the directory. Pick order: when a neighbour is hungry, the outbox has room and at
  least two tasks wait, the **oldest** fork task (it then takes the ordinary step-11 path in S_LINK:
  REF interaction counted, SPAWN to the hungry neighbour); otherwise the stack top; the **newest** fork
  task only when the stack is empty. `hungry`, quiescence and the spawn thresholds count stack + deque.
  Mode (`+s14`, mesh input `fork_dq`): 0 = off (step 13, cycle for cycle), 1 = every fork definition
  (directory bit 56), **2 = default: fork definitions that are not stream-fed** (loader bit 59: the fork
  SCC calls no producer recursion; qsort's partitions are lists that `lo` / `hi` emit piece by piece,
  and handing its oldest task away moves the consumer away from its producers: +5% / +7% cycles on
  4×4 / 8×8 in mode 1). **Step 15** narrows bit 59 further, in the loader only (no RTL change): a fork SCC
  is also left out when it is *data-walking*, i.e. one of its templates takes its first argument apart
  as a Scott value (the root's argument var meets a CON node in a template redex: treesum's `tsum` walks
  gen's tree, `qs` a list), as opposed to a numeric fork that switches / computes on its argument (fib,
  gen, the direct tsum). A given data-walking task leaves the structure it walks at the giver, so every
  match step crosses the mesh: treesum(9) 8×8 under step 14 sent 0.526 msgs/interaction, 0.466 with
  step 15's bit 59 (and 5.7% fewer cycles). `OMEGA_DQF_DATA=1` restores step 14's bit 59.
* **Governor relax with a hungry neighbour (step 14, knobs).** `+govnb` = k (mesh input `gov_nb`, 0 = off):
  at epoch end a cell with a hungry neighbour that sent at most k/4 × the budget relaxes one level (this
  test comes before the over-budget test); `+govl0` = reset level (step 13: 2). The fabric study's nb5l1
  (k = 5, reset level 1) regresses list / higher on the RTL (4×4: list(120) +4.8%, higher(100) +9.8% at
  0.52 msgs/int; 8×8: list +9.5%, higher +5.5%), and the milder k = 3 is a wash (qsort 4×4 −1.7%, 8×8
  +2.7%), so the relax is **off by default** (k = 0, reset level 2: the step-13 governor); the knob stays
  for experiments (README step 14, known gap 12).
* **Memory pressure (step 4).** Each cell also drives a 1-bit `roomy` wire: free node slots and free
  var slots both ≥ SLOTS/4 sets it, either < SLOTS/8 clears it (hysteresis, so the wire does not
  toggle on every allocation). `hungry` additionally requires `roomy`, so a full cell never asks for
  work. A cell that lacks slots moves work from poor to rich instead of retrying in place:
  * a SPAWN it cannot expand goes to a roomy neighbour (round robin over all neighbours only when none
    is roomy);
  * a SWI ~ #n>0 that needs a slot sends the SWI node as `NODE` to a roomy neighbour (the partner is a
    number, so the rule runs there);
  * a commutation that needs 2 node + 4 var slots sends P as `PULL` to a roomy neighbour, which pulls Q
    after it (§4);
  * only when no neighbour is roomy does the task go back on the stack as a retry, as before.
* **Retry slot and global pressure (step 10).** Since step 10 the retry of the last bullet, and a SPAWN
  that has neither room nor a roomy neighbour, no longer go on the LIFO task stack (where they were
  popped again at once and starved the tasks that free memory) nor round robin to any neighbour. Each
  cell has **one non-LIFO retry slot** (`rs_v`, `rs_e`, a timer `rs_tm` loaded with the run-time input `rto_m1` (an input since step 18; default 8 cycles since step 19, 32 before), a park count
  `rs_n`): the retry is parked there, the engine keeps working on its stack and messages, and the
  parked entry is taken (before the stack) when its timer expires. A retry taken from the slot that has
  to park again counts up `rs_n`; on the 4th consecutive park the task **escalates**: a SPAWN is
  forwarded round robin (the old rule), a SWI node is sent as `NODE` and a commutation node as `PULL`
  to the next neighbour round robin even though it is not roomy. Escalation moves work across cells
  that are only partly full toward room several hops away (a roomy neighbour still always wins). The
  slot is single: a second retry while it is occupied takes the old path (stack / round robin), so no
  retry can be locked out of the slot forever. A parked entry keeps the cell non-idle and non-hungry
  (§8). Mutants 39–41 (parked entry never taken, quiescence ignoring the slot, no escalation).
* **Room-distance gradient (step 19).** Each cell registers a 3-bit room distance `rdist` (0 when
  `roomy`, else 1 + the smallest `rdist` of its neighbours, saturating at the run-time cap `rgrad`;
  `rgrad` = 0 switches the gradient off and gives the step-18 behaviour cycle for cycle) and sends it to
  its neighbours next to `roomy`. A neighbour with a smaller `rdist` is *downhill*. With a downhill
  neighbour (a) a SPAWN that has neither room nor a roomy neighbour is forwarded downhill at once instead
  of being parked; (b) escalated retries (SPAWN, SWI `NODE`, commutation `PULL`) go downhill instead of
  round robin; (c) an expansion must leave `rsv` free node and var slots (3-bit run-time input since
  step 20, default 1; step 19 had the constant `RSV19` = 4, `+rsv=4` reproduces it), so a poor cell on the
  path does not spend its last slots and then block its ejection port on a `NODE` / `PULL` arrival that
  needs a free slot (one slot is enough for that; 4 also kept 8-free-slot cells from running any 5–6-node
  expansion, README step 20); (d) with `rgrad` ≠ 0, a `NODE` / `PULL` at the head of the ejection queue of a cell
  that has no free node slot at all and nothing else to pick (no task, no expired retry) is passed on
  unchanged to a roomy neighbour, else a downhill one, else the next neighbour round robin, instead of
  blocking the head (the `LINK`s queued behind it can be what frees the cell: a head-of-line deadlock seen
  on the RTL at `rto` = 8 with and without the gradient, global treesum(7) 8×8). Without a downhill
  neighbour (no room within `rgrad` hops, or the whole fabric full) rules (a)–(c) are the step-10 rule. Default `rgrad` = 3 with `rto` = 8 (README step 19: the short
  timeout alone livelocked the fabric and the RTL under global pressure; the gradient removes that).
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
  Mutants 49 (no downhill neighbour is ever found), 50 (rule (d) off) and 51 (the reserve applied without a
  downhill neighbour). At the default reserve 1 a cell reaches zero free node slots only where the reserve does
  not apply or never had one; the step-21 mempress cases (ballast leaves no free node slot in the program's home
  cell (0,0)) stop on every run without rule (d) and catch mutant 50 at the default configuration.
  None of these change the result or the interaction count (migration is not an interaction), only
  where a rule runs. `tests/test_mempress.py` pre-fills cell (0,0) with foreign "ballast" so that only
  4–30 slots are free there: without the mechanism the v3 RTL livelocks on 7 of 30 such cases.
* **Task stack.** Depth-first (LIFO) order keeps live memory small (HVM2 uses per-thread stacks for the
  same reason). Retry tasks (`K_SPAWN`, re-queued `LINK`) reuse it.
* **Expansion order (step 23, `+ilr` / `OMEGA_ILR`, 2-bit run-time input, default 0).** `ilr` = 0 (step 22
  cycle for cycle): the last `S_EXN` cycle links the definition's root to its partner at once (`S_EXN` →
  `S_LINK`), while the definition's redexes wait on the stack. `ilr` ≥ 1: the expansion is marked deferred when it
  starts (`ex_dfr`, latched for the whole expansion), and if the definition has at least one redex the first
  writing `S_EXN` cycle pushes the root link `{K_LINK, x, root}` *below* that cycle's redexes (it needs one more
  stack-cache entry: `tq_room` ≥ 2 / 3 instead of 1 / 2); the last cycle then picks the next task (`fin`) when it
  pushed nothing, else goes to `S_IDLE` (this cycle's pushes are visible next cycle). The definition's internal
  redexes, and everything they push, are reduced before the root is linked, as the fabric model always does
  (`Cell.expand`). `ilr` = 2 also uses the fabric model's child order: erase / copy continues with aux 2 and
  pushes aux 1, annihilation continues with aux 2 ~ aux 2 and pushes aux 1 ~ aux 1, commutation continues with
  the fourth new link (b2 ~ P copy 2, read through the `S_WQ` bypass) and pushes the other three in the model's
  order, so the pop order equals the model's (step 22: the first new link continues). The admission check of an
  expansion already reserved a stack entry for the root (`tq_tot + nr + 1 < QDEPTH`). The orders change only the
  schedule, never the result or the interaction count. Effect (one 1×1 cell, `rtl.run` peak node / var slots,
  README step 23): treesum(9) 281 / 463 at `ilr` 0, 159 / 238 at 1, 73 / 123 at 2 (fabric model 75 / 118),
  so it finishes with 460 / 235 / 120 free slots; but the order is program dependent: qsort(40) 769 → 848 → 1,282
  vars, fib(20) 158 → 269 → 278, sum(1000) 3,008 → 3,010 → 4,005 vars with a task stack of 1,005 → 2,003 entries
  (a linear recursion keeps one deferred root link per level). On 2×2 / 4×4 deferring the root delays the work
  the root link exposes to other cells (list(120) +31%, higher(100) +22–38% cycles), so `ilr` stays a knob.
  Mutants 53 (the root is linked at once whatever `ilr` says) and 54 (`ilr` = 2 without the child order).
* **Owner tags.** 4 bits in each node RAM word (`{owner, aux2, aux1}`) and var RAM word (`{owner, port}`); see §12.
* **Rule execution.** Reading both nodes, applying the rule, writing up to four node slots and
  launching the first resulting link take one cycle. Every further link costs one PUSH cycle, and is
  later popped as a task. The first link is processed immediately (tail-call), with no push.

### 5.1 Engine cost table (cycles, v4 RTL: step 9)

| operation | cycles |
|---|---|
| pick a task or message | 0 (chosen in the cycle that finishes the previous step; 1 only after real idleness) |
| each link step (local var exchange, chain step, or remote send) | 1 (RAM data read one cycle ahead, write bypass) |
| redex rule, including its node writes and the first resulting link | 1 (same cycle as the link step) |
| extra node writes of a commutation / SWI | v4: the rule cycle writes two node slots (node RAM write ports 1 and 2); the remaining two commutation copies and the four var-tag writes go in **one** `S_WQ` cycle (both ports, both bypassed into the read-ahead). Commutation 2 + 3 cycles (v3: 2 + 4); SWI needs no `S_WQ` cycle |
| each extra resulting link | 1 push now, 1 link step when popped |
| SPAWN decision (hungry / roomy neighbour scan) | same cycle as the rule |
| EXPAND (v4): up to 8 node + 8 var slots mapped per cycle (first batch in the rule cycle), then **two** entries per cycle: nodes *i*, *i*+1 (node write ports 1, 2), var tags *i*, *i*+1 (var write ports 1, 2), redexes *i*, *i*+1 (two task pushes) (`S_EXN`) | ≈ ⌈max(nn, nv, nr)/2⌉ + allocation cycles beyond the first batch; the root link follows as an ordinary link step |
| var chain step handed to the var-hop unit (VHU, §5.4) | 0 for the main engine (it picks its next task in the same cycle); the VHU does 1 exchange per cycle in parallel |
| router hop (FIFO to neighbour FIFO) | 1 per hop (+ jitter) |

Measured: fib(20) on one cell, **v4 (step 9) 2.36 cycles per interaction** (fib(12): 14,831 cycles /
6,274 interactions; fib(20) in the README benchmark table), v3 3.41, v1 register-file cell 5.30, v2
SRAM cell 8.82. The Python fabric model charges per-task costs and is approximate (±20%); only RTL numbers are
reported as cycles.

### 5.2 Synthesis and area normalisation

`synth/synth_cell.ys` (Yosys 0.70, `techmap; abc` to generic gates, memories kept as `$mem_v2`), GE =
NAND2 equivalents from `synth/ge.py`. One v3 cell at 1024 slots (`results/synth/stat_v3_cell_1024.txt`):
155,725 generic cells, 4,271 flip-flops, **233,164 GE**, 8 memory macros, 1,177,600 bits (node
1024×132, var 1024×68, task stack 1024×130, free stacks 2×1024×10, node ROM 4096×128, redex ROM
2048×128, directory 256×128). Area-normalised cost of a run = cells × GE per cell × cycles, compared
with TACHYON-128's 217,636 GE × its cycles for the same program; memories are excluded on both sides
(README, "Comparison").

### 5.3 Cluster definition ROM (step 7, `rtl/omega_rom.sv`)

The node-template ROM (4096 entries) and the redex-template ROM (2048 entries) were replicated in every
cell: 786 Kbit of the cell's 1.18 Mbit. They are now one `omega_rom` per **cluster** of CW×CH cells
(`omega_mesh` parameters `CW`, `CH`, `RPORTS`; default 2×2 with one read port). The per-cell
directory (256×128 b) stays in the cell, because it is read ahead on every link step.

* **Four-entry words (v4, step 9; step 7 used pairs).** One ROM word holds four template entries
  (512 b). The loader aligns every definition to a multiple of four entries (`fabric.Image` pads with
  empty entries). The v4 EXPAND writes two entries per cycle, so one grant still feeds two EXPAND
  cycles; the cell keeps the last word it received (`bufn`/`bufr`, 1024 flip-flops) and uses an
  arriving word directly. (Step 7 text below says "pair": read "word".)
* **Request / grant.** A cell's request is combinational from registers only: in `S_EXN` the pair of
  entry `ex_i` (held) or `ex_i + 1` (advancing) unless that pair is already buffered or arriving; in
  `S_EXA` pair 0; in `S_LINK` pair 0 of the definition whose directory word was read ahead, when the
  link may start an expansion here (dQ is a REF not handed to a hungry neighbour). The arbiter grants
  up to `RPORTS` requesters per cycle from a rotating priority pointer (round robin: a requester
  waits at most ⌈NC/RPORTS⌉ − 1 cycles); the data is the synchronous ROM read, steered back one cycle
  later. A cell that misses a grant re-requests and its `S_EXN` step holds until its pair arrives.
  The buffered pair is dropped when a new expansion starts.
* **Correctness does not depend on the arbitration**: a missed grant only delays an EXPAND step.
  Mutants 29–31 (grant beyond the port count, EXPAND not waiting for its pair, stale buffered pair)
  are caught by the regression.
* **Options measured** (fib(15) / treesum(7), RTL cycles; full table in the README):

  | ROM organisation | storage per cell | 2×2 mesh fib(15) | 4×4 mesh fib(15) |
  |---|---|---:|---:|
  | replicated (v3, one per cell) | 786 Kbit | 23,784 | 6,881 |
  | 2×2 cluster, 1 port, one entry per word | 197 Kbit | 32,182 (+35%) | 8,893 (+29%) |
  | 2×2 cluster, 2 ports, one entry per word | 197 Kbit × port cost | 24,403 (+3%) | 7,195 (+5%) |
  | **2×2 cluster, 1 port, pair words (default)** | **197 Kbit** | **24,118 (+1.4%)** | **7,174 (+4%)** |
  | 4×4 cluster, 1 port, pair words | 49 Kbit | — | 12,444 (+81%) |
  | 4×4 cluster, 2 ports, pair words | 49 Kbit × port cost | — | 7,594 (+10%) |

  Pair words buy the bandwidth of a second port without the second port. A 4×4 cluster with one
  port is bandwidth-bound (fib expands a definition every ≈9 interactions).
* The Python fabric model reserves a cluster port for ⌈max(nn, nr)/2⌉ cycles per EXPAND
  (`Fabric(cluster=(CW, CH, NP))`); it is an approximation of the cycle-by-cycle round robin.

### 5.4 v4 engine (step 9): wide EXPAND, shorter commutation, var-hop unit

* **Second write ports.** The node RAM and the var RAM get a second write port (`n_we2`/`v_we2`).
  The read-ahead bypasses both write ports (mutants 32, 38). Area: both RAMs become 2W macros
  (+50% macro area each in the fakeram45-density model of §5.2 / README step 8).
* **Wide EXPAND.** Entries *i* and *i*+1 (node, var tag, redex) are written in one `S_EXN` cycle; slot
  allocation maps up to 8 node + 8 var slots per cycle, and every slot of the definition is mapped
  before the first write (a template port may name any node / var of the definition). ROM words hold
  four entries (§5.3). Mutants 26, 33, 34.
* **Commutation.** The rule cycle writes the reused slot and one fresh copy (two ports); the other two
  copies and the four fresh var owner tags drain in one `S_WQ` cycle (mutant 23: second queued write
  dropped).
* **Var-hop unit (VHU).** A link whose A side is a local, correctly tagged var is handed to a second
  small engine instead of being followed by the main engine, which picks its next task in the same
  cycle. The VHU has its own var read port (read ahead) and uses var write port 2: an empty var takes
  B and the VHU is free; a substituted var is freed and the chain continues while the next link again
  has a local var on one side; any other link (redex, remote var, failed owner check) is handed back
  (`vh_o*`) and the main engine takes it before the task stack. The VHU yields write port 2 to the main
  engine and stalls while the main engine's current link names the same var slot, so every var
  exchange remains atomic (single owner per var slot). `hungry` and `idle` include "VHU idle".
  Mutants 35–38 (no stall on the same slot, hand-back never taken, VHU disabled = performance mutant
  caught by a cycle bound, no bypass of write port 1 into the VHU read-ahead).
* **Free-var cache overflow fix.** A VHU exchange that frees a var slot only proceeds when the free-var
  cache has room for the push (`vf_room`); before the fix a burst of chain steps could overflow the
  cache in rare schedules (treesum(7) 2×2 fuzz case hung).
* The fabric model mirrors the VHU (`Cell.vhu_chain`) and the v4 costs; it stays cycle-approximate.

## 6. Loader and readback

`fabric.Image` instantiates `@main` into cell (0,0). With `scatter`, it instead places every node and
var in a random cell, a fuzzing option that creates heavy cross-cell traffic from cycle 0. It reserves
the **root var** at cell (0,0), var slot 0, and puts `link(main_root, VAR root)` plus main's redexes on
cell (0,0)'s task stack. It also emits the ROM. The RTL reads everything with `$readmemh`. After
termination the testbench strobes `dump`, every cell writes its node RAM, `nalloc` tags, var RAM and
counters, and `readback_dump` walks the graph from the root var:
* var chains are followed to their end;
* a var with NONE becomes a named variable (renamed by first appearance);
* `NUM` becomes `#n`, and nodes print in IR syntax.

The result is a canonical string, for example `#6765` or `((x0 x0) (x1 x1))`.

## 7. Back-pressure and deadlock

* **Network.** XY dimension-order routing on a mesh is deadlock-free provided the ejection port is
  always eventually drained.
* **Ejection is always drained.** The engine never blocks on its outbox. If the outbox is full, a send
  turns into a retry task on the local task stack (`LINK` becomes `K_LINK`, `SPAWN` becomes `K_SPAWN`,
  and a NODE migration becomes a re-queued redex because the node is simply not freed). Message
  consumption therefore depends only on task-stack space, never on the network, which breaks the
  classic request-reply cycle. When the outbox is full, the engine prefers ejected messages.
* **NODE needs a free slot.** A NODE message waits in the eject FIFO only while the cell has zero free
  node slots.
* **Resource exhaustion.** These cases are reported, not hidden:
  * task-stack overflow: `err = 1`, the cell halts and the testbench reports status 2;
  * a 1×1 fabric unable to place an expansion: `err = 2`;
  * a fabric that is globally full can bounce SPAWNs forever. The Python model stops with "no progress
    for 100000 cycles" and the RTL testbench with a cycle limit (status 3). Since step 10 parked
    retries poll every `rto` cycles (`+rto`, step 18; default 8 since step 19) instead of every cycle, but escalated SPAWNs (and SPAWNs that find the
    retry slot occupied) still bounce; `tests/test_mempress.py` checks that a globally full fabric ends
    in status 3 without a wrong answer.

  All are Known gaps (§11).

### 7.1 Progress: what the memory-pressure rules guarantee (step 20)

Interaction nets give *safety* for free: every rule is local, re-homing a node or a SPAWN is not an
interaction and is location free, so whenever a run ends its normal form and interaction count are the
semantic reducer's (strong confluence). *Liveness* is a different matter. The argument below is what the
default (`rto` = 8, `rgrad` = 3, `rsv` = 1) gives and where it stops; it is an argument, not a machine-checked
proof.

1. **No network deadlock while node slots exist.** XY routing has no cyclic channel dependency, so the mesh
   deadlocks only if an ejection port stops draining. Its head can stall only on a `NODE` / `PULL` in a cell
   with zero free node slots (LINK, SPAWN never wait for a slot: a SPAWN without room parks or moves on). In
   such a cell every task either finishes in bounded time (sends never block: a full outbox turns them into
   retries, §7) or leaves it (homeless expansions, SWI moves and commutations park for `rto` cycles and leave
   on the fifth try), and annihilations free slots. So the cell eventually has nothing else to pick, and rule
   (d) of §5 then passes the head on. With a downhill neighbour, `rsv` ≥ 1 keeps an expansion from taking a
   cell's last node or var slot in the first place.
2. **Placement is live inside the gradient.** Let cell R stay `roomy` (≥ SLOTS/8 free slots, more than any
   definition of the suite plus `rsv`; a 255-node definition would need SLOTS ≥ 2,096 for this). Once
   `rdist` has settled (it is registered, so ≤ `rgrad` cycles after R's `roomy` bit settles), a SPAWN within
   `rgrad` hops of R that does not fit moves to a neighbour with a strictly smaller `rdist` at every failure
   (rule (a), or rule (b) after parking), so it reaches a roomy neighbour, which takes it, within `rgrad`
   hops. Farther away all cells read `rdist` = `rgrad`, nobody is downhill, and escalated retries move
   round robin: a rotor-router walk, which for a single walker visits every cell within O(|E|·D) moves
   (Yanovski, Wagner, Bruckstein 2003). The rotors here are shared with other traffic and the retry slot holds
   one task, so beyond `rgrad` hops this is a plausibility argument only.
3. **No completion guarantee.** (i) A fabric with too little memory in total cannot finish (`OVERFULL`,
   status 3). (ii) Nor can one with *enough* memory if the parallel order needs more than the fabric has: the
   peak live graph depends on the reduction order, and the fabric picks the order locally. Counterexample
   (README step 20, `results/s20/cex.py`): treesum(9) runs on one cell with 115 free node / var slots, but on
   3×3 with 8 free slots in each of 8 cells and 200 in the ninth (264 in total) the default stops on 20 / 20
   seeds. In the stopped state every pending task is a SPAWN, the free var slots are fragmented (≤ 4 per cell,
   every definition needs ≥ 5) and the live graph holds more than twice the sequential peak, so *no* schedule
   can continue. Therefore no local re-routing mechanism (hop budget, escape network, bounded detours) can
   give a progress guarantee: there is nowhere to put the work. A guarantee needs memory-aware admission
   before the fabric fills (e.g. a global low-memory mode that stops giving work away and reduces depth first,
   bounding the peak by the sequential one) or spilling to off-fabric memory. Until then, running out of
   memory is detected (status 3 / "no progress"), never silently wrong. Step 24 (§7.2) closes the gap
   statically for the Ω-L subset: the compiler bounds the peak over every schedule, and a fabric whose cells
   have that many slots cannot reach this state. Step 25 (§7.4) adds the admission of (ii) for a multi-tenant
   fabric, in the fabric model: Ω-L jobs start only while the sum of their bounds fits every cell.
4. **Low-memory watermarks (step 22, §5).** With `lm` = 2 the counterexample above finishes on 20 / 20 seeds
   (fabric model, corner 120–1024 free slots) and the RTL counterpart (corner 470–1024, 30 seeds, the RTL needs
   451–470 free slots for treesum(9) on one cell) on 30 / 30; finished runs take about the 1×1 time. This is
   the admission idea of (ii), not a guarantee: a program whose depth-first order on one cell needs more than
   any cell has, or memory spread thinner than `lm_hi` slots per cell, can still stop (detected, status 3).

### 7.2 Ω-L: a compile-time peak-memory bound (step 24, `omega/eal.py`)

§7.1 (3) leaves completeness open because the peak live graph depends on the schedule, which the fabric picks
locally. Step 24 closes it *statically* for a typed subset: for a program the compiler accepts, it computes a
number B such that **no schedule** of that program ever has more than B live nodes or vars, so a cell (or
every cell of a mesh) given B slots can never hit the memory stall of §7.1 (status 3 / "no progress").

**Bound.** For a net that normalises, every maximal reduction fires the same multiset of interactions: two distinct
active pairs share no node, so firing one leaves the other in place with the same rule (diamond property; the
interaction count of §9 is the one-number shadow of this). Each rule instance has a fixed node delta Δ (expansion of
definition d: +|d.nodes|; commutation +2; `SWI` on a non-zero number +1; `OPR` swap 0; everything else < 0) and a
fixed number of var allocations (expansion |d.vars|, commutation 4). Hence

    B_nodes = n0 + Σ_i max(0, Δ_i)        B_vars = v0 + Σ_i (vars allocated by i)

are properties of the program, not of a schedule (n0 / v0: the loaded `@main` template and the root var). After
any schedule prefix P the live node count is n0 + Σ_{i∈P} Δ_i ≤ B_nodes and the live var count is at most the vars
allocated so far ≤ B_vars. This holds for every implementation that frees a rule's consumed nodes in that rule
and allocates exactly the rule's slots: the semantic reducer, the fabric model and the RTL (a `NODE` / `PULL` in
flight holds no slot; var slots are freed by the second arrival, which only lowers the live count).
Vars use allocations, not deltas, because which interaction frees a var depends on which side arrives second.

**No memory stall.** One cell with B_nodes node slots and B_vars var slots never lacks room: an expansion needs
|d.nodes| free slots, and live-before + |d.nodes| = live-after ≤ B. On a mesh every cell is given
`slots_mesh` = max(B_nodes, B_vars) + D_max + max(`lm_rsv`, `rsv`) slots (D_max = the largest template, 12 in the
suite): no cell can hold more than the whole live graph, so every cell always keeps at least D_max + 16 free, every
expansion fits where it is (the reserve never forces a hand-off) and every `NODE` / `PULL` finds a slot (rule (d)
is never needed). Not covered: the task stack (`err` 1, status 2: sum(1000) needs a 1,005-entry stack on one
cell), cycle limits, and programs outside Ω-L.

**Ω-L (the subset).** The counting needs a terminating program; Ω-L is a light-affine, stratified (box depth 1)
subset of Ω-lang whose programs all terminate. `eal.check` adds four rules to the frontend's checks:

* **T (types).** Hindley–Milner as in §10, but every constructor field has *one* type in the whole program
  (step 6 gave it a fresh type at every use) and no field holds a function. Otherwise data can hide self
  application: `data Box = B(f)`, `def w(x) = unbox(x)(x)`, `def main = w(B(w))` is accepted by step 6 and loops.
* **A (affinity).** A binder whose type is not `Num` is used at most once in every net template the compiler
  emits, counted exactly as `Compiler.compile_def` counts (after arm lifting: an inline value arm shares its
  binders with its siblings, a lifted arm gets them as one argument each). Numbers are free to duplicate
  (`DUP ~ NUM` copies an atom); a data value never is, so a match takes every data cell apart at most once.
  A binder whose type is still a type variable counts as non-number (conservative).
* **! (duplicable closures).** A binder of function type may be used several times only if it is a parameter of
  its definition (a !-parameter: `map`'s and `foldr`'s `f`, `twice`'s `f`), and every call site passes there an
  *inert closure*: a λ literal over its own variables, numbers, operators and applications, whose free variables
  are numbers or the caller's !-parameters, or a definition name, or the caller's own !-parameter. Nothing that
  is duplicated contains a definition reference, so a copy costs at most the literal's node count and never
  copies pending work (box depth 1). Partial applications of a definition with a !-parameter are rejected.
* **R (recursion).** In every strongly connected component of the call graph each recursive call decreases a
  measure parameter of its callee (one per definition, found by search): a *structural* sub-term (a field of a
  `match` on that data parameter, at any depth, through `let` aliases) or a *guarded numeric* predecessor (`p` of
  `switch n`, `n - k` / `p - k` where an enclosing `switch n`, `if n < c`, `if n <= c`, `if n == 0` proves that
  the u32 subtraction cannot wrap). A recursive definition used as a value (recursion through a closure) is
  rejected; so are lexicographic measures (Ackermann).

Termination (an argument, not a machine-checked proof): a recursive call only unfolds when its lifted arm is
selected by a `SWI` / `match` on a value, and the measure strictly decreases on a well-founded order (u32 without
wrap, or sub-terms of a finite first-order data value); the rest is an HM-typed λ-calculus, which is strongly
normalising, and rule T keeps functions out of data; rules A and ! bound every copy by a static size.

**Computing B.** EAL / LAL give *generic* bounds (elementary / polynomial in the input size), and Ω-L's
stratification gives the same kind: per component, a numeric recursion with fan-out c unfolds ≤ c^n times
(`eal.growth`), a structural one once per data cell, composed along the component DAG into a tower whose height
is the DAG depth. These are sound but useless as slot counts (fib(20): ≤ 2^21 calls × 15 template nodes
≈ 3.1·10^7 against B_nodes = 262,690). Since an Ω-L program terminates, the compiler instead runs a
**counting reduction** of the closed program once (`eal.bound`: the semantic reducer's rule bookkeeping, no
placement or messages; treesum_direct(14), 245,750 interactions: 1.7 s) and reads B off exactly. This is
compile-time partial evaluation of a closed program, not a symbolic bound in N (step 25 derives that
form from the counts, §7.3); the CLI reports both:

    python3 -m omega.eal programs/treesum.olm --N 9      # or: python3 -m omega.eal treesum 9
    programs/treesum.olm: in Ω-L
      recursion gen: numeric on parameter 1, ≤ 2^value unfolds
      recursion tsum: structural on parameter 1, linear in its size
      bound: nodes 18921, vars 16365 (n0 2, v0 3, 18410 interactions)
      depth-first peak (semantic): nodes 67, vars 97
      slots: one cell 18921, every mesh cell 18943 (largest template 6)

**How tight.** B is a bound over *all* schedules, so it cannot be below the worst schedule. A tighter all-schedule
bound for nodes is the max-weight closure W of the causal event DAG (`results/s24/worst.py`: an interaction
depends on the events that created its two nodes and on those whose links joined the wire that made the pair
active; live nodes after a prefix = n0 + the weight of a causally closed set; W = n0 + max closure by min cut).
W is the same from six different recorded orders (7 programs, small N). B / W = 1.7–2.9 on the suite (9.2 for
sort); breadth-first order comes close to W for the fork programs (treesum(9): 5,375 of 7,166), and over every
schedule measured (5 semantic orders, fabric 1×1 / 2×2 / 4×4, RTL 1×1) B is 2.2–23× the largest node peak and
1.3–13× the largest var peak.
The depth-first peaks the fabric and the RTL reach are far lower (README step 24: at the sizes the RTL check runs, B is 5–102× the RTL 1×1 peak in nodes and 2.3–35× in vars, and the ratio grows with N for the exponential programs), so
B answers "is this program safe on this fabric under any schedule", not "how small can a cell be".
Step 25 adds a var analogue W_vars that holds for atomic links only (§7.3), so the cells are still sized by
max(B_nodes, B_vars).

**Which programs.** In Ω-L: fib, sum, fact, list, treesum, treesum_direct, sort, higher (8 of the 9 suite
programs) and 10 of the 15 frontend unit programs. Rejected: qsort (A: `t` goes to both `lo(h, t)` and `hi(h, t)`;
R would reject `qs(lo(h, t))` too), Church `two(two)` (box depth 2), Ackermann (lexicographic), a default binder that
aliases the scrutinee (A: `other` copies the matched value), a pair with a number in one place and a constructor in
another (T), a list of functions (T). Checker / bound mutants (`OMEGA_EAL_MUT` 1–7, `tests/test_eal.py --mutants`)
are all caught.

### 7.3 B as a closed form in the input size, and a causal var bound (step 25, `omega/symbolic.py`, `omega/causal.py`)

§7.2 reads B off one counting run per concrete N. Step 25 derives **B_nodes(N)** and **B_vars(N)** in closed form.

**Why a closed form exists.** Every rule instance has a fixed node delta and var count (§7.2), so B(N) is a sum of
per-interaction constants over the interaction multiset of the program at size N. Rule R (§7.2) allows only
structural recursion and recursion on a guarded numeric predecessor `n - k` with constant k. When the work done for
N is fixed by N alone (no data-dependent branch whose arms cost differently), the number of unfoldings of every
definition is a C-finite sequence in N: a numeric recursion `f(n) -> f(n-k1) … f(n-km)` contributes the
characteristic factor x^K − Σ x^(K−kj) (fib: x² − x − 1; `tsum(p) + tsum(p)`: x − 2), a structural recursion over a
value built by such a recursion inherits that value's size sequence, and straight-line work adds factors (x − 1).
So B(N) satisfies a linear recurrence with constant coefficients whose dominant root R bounds: at most the largest
numeric fan-out of the program (1 when it has none).

**Derivation** (`symbolic.analyse`): (1) count B(N) exactly for N = 0, 1, … (the §7.2 counting run, until one run
takes 4 s or B passes 400,000); (2) find the shortest linear recurrence from a start N0 ≤ 4 by Berlekamp–Massey over
exact rationals, fitted on the first 2L + 2 terms only; (3) solve it: rational roots of the characteristic
polynomial (with multiplicity m: N^j r^N, j < m) and, for an irreducible rest, its fundamental sequence U (U = the
Fibonacci numbers F for x² − x − 1); coefficients by exact Gaussian elimination; (4) **certify**: the closed form
must equal the counted B(N) at every N of the range, the terms after the 2L + 2 fitted ones being held out, and its
dominant root must not exceed R's limit. Terms below N0 are given as a table (piecewise form).

**Data-dependent cost.** When no recurrence of length ≤ (range − 4) / 2 reproduces the sequence (sort: insertion
sort's comparisons depend on the pseudo-random data), the tool falls back to the tightest **upper envelope** in a
basis R allows (polynomials of degree 1–3, c^N for the numeric fan-outs; vertex enumeration of the LP "minimise the
total gap subject to envelope ≥ B(N)", non-negative leading coefficient), fitted on 2/3 of the range and checked on
the rest, or, if no basis survives that, fitted on the whole range (then no claim is made beyond it). For sort a
program-level argument gives a data-independent bound instead (README step 25): B(N) = a + b·N + c·I + d·nil
exactly (I: insert steps that go on, nil: inserts that end at Nil), and I ≤ N(N − 1)/2, nil ≤ N give the bound over
every input of length N.

**What is certified.** Exactly what was checked: B_sym(N) = counted B(N) (exact forms) or ≥ (envelopes) on every N of
the reported range, plus, in `tests/test_s25.py`, on 1–4 values of N past it that the fit never saw. Beyond the
range an exact form rests on the C-finite argument above (an argument, not a proof: it assumes the per-N work is
fixed by N), an envelope on nothing.

**Results (suite).** All exact except sort, from N = 0 (no table needed):

| program | B_nodes(N) | B_vars(N) | growth (R allows) | certified on N = |
|---|---|---|---|---|
| fib | 24·F(N+1) − 14 | 19·F(N+1) − 11 | φ^N (2^N) | 0..21 |
| sum, fact | 11·N + 7 | 8·N + 6 | linear (1) | 0..60 |
| list | 54·N + 27 | 56·N + 23 | linear (1) | 0..60 |
| higher | 43·N + 42 | 44·N + 43 | linear (1) | 0..60 |
| treesum | 37·2^N − 23 | 32·2^N − 19 | 2^N (2^N) | 0..13 |
| treesum_direct | 12·2^N − 8 | 9·2^N − 5 | 2^N (2^N) | 0..15 |
| sort (descending input, worst case) | 29/2·N² + 97/2·N + 24 | 27/2·N² + 85/2·N + 20 | N² | 0..45 |
| sort (ascending input) | 84·N + 3 (N ≥ 1) | 74·N + 2 (N ≥ 1) | linear | 0..45 |
| sort (its own pseudo-random input), any input of length N | ≤ 29/2·N² + 139/2·N + 24 | ≤ 27/2·N² + 121/2·N + 20 | N² | decomposition exact on 1..45 |

**Causal var bound W_vars** (`causal.bound`). Event e allocates a(e) vars; var v is freed by the second arrival at
it, i.e. once every event of F_v (the events whose links reach its two ends, through substitution chains) has
happened. When F_v has a causal maximum m_v, "v freed" = "m_v done", so W_vars = v0 + max closure of
a(e) − #{v : m_v = e} (vars without a causal maximum count as never freed). Suite (§7.2 sizes): B_vars / W_vars =
1.1–2.4 (fib(10) 1,680 / 1,254, sort(15) 2,435 / 1,010). **W_vars bounds the semantic reducer only**: the fabric and
the RTL free a var when a LINK task or message is processed, any number of cycles after the interaction that created
it, so the live var count there can exceed every closed-prefix value. Admission (§7.4) therefore uses W_nodes and
B_vars. The task stack is still not bounded: atoms (ERA, NUM, REF) occupy no slot, so pending pairs are not bounded
by node and var slots; a bound needs an atom count per rule.

**CLI.** `python3 -m omega.eal --symbolic treesum [NMAX]` (or a `.olm` file with an `N`):

    treesum: Ω-L, symbolic bound in N (counted and certified on N = 0..13)
      recursion gen: numeric on parameter 1, ≤ 2^value unfolds
      recursion tsum: structural on parameter 1, linear in its size
      B_nodes(N) = 37·2^N - 23   [exact]
        growth 2^N (R allows <= 2^N); B_sym / counted: max 1.000, mean 1.000; sound on the range: True
      B_vars(N) = 32·2^N - 19   [exact]
        ...

### 7.4 Memory-bound admission control (step 25, `omega/admission.py`, fabric model)

§7.1 (3) names admission before the fabric fills as the missing piece for a completion guarantee; §7.2 / §7.3 give
the number to admit by. A job is a program with an owner (§12). An Ω-L job reserves **(W_nodes, B_vars)** (W_nodes
is sound on every implementation in which a node in flight holds no slot, so the live node count after any moment
is n0 + the deltas of a causally closed set of interactions; W_vars is not, §7.3); `bound="B"` reserves (B_nodes, B_vars).

**Rule.** With S node and S var slots per cell, a queued Ω-L job is started only if, for nodes and vars alike,

    Σ (reservations of the running Ω-L jobs) + its own  ≤  S − margin,   margin = 0 on one cell, D_max + max(LM_RSV, RSV) on a mesh.

Tenants share no slots, so the live graph of all running Ω-L jobs never exceeds the sum of their reservations, no
cell can hold more than that, and every cell keeps at least D_max + the reserve free: every expansion fits where it
is (the reserve never forces a hand-off) and every NODE / PULL finds a slot (rule (d) of §5 is never needed). This is
§7.2's argument applied to a sum of jobs, so the fabric never reaches the memory stall of §7.1 (3), and no job can
take another's memory. **Liveness:** jobs start in arrival order (FIFO, no overtaking); Ω-L jobs terminate, so a
queued job waits only for running jobs to finish. A job whose reservation exceeds the empty fabric's budget is
rejected at submission. One job per owner runs at a time (completion is detected per owner).

**Completion and release.** A job is done when its root var holds a value and no task, retry slot, var-hop link or
message anywhere carries a capability of its owner; the scheduler reads the result back, frees the owner's remaining
slots (the result went to the host) and releases the reservation. A queued job is loaded like the static image
(§6): its root var in its home cell, its `@main` nodes and vars from free slots starting there, its links on the
home cell's task stack.

**Untyped jobs** (not in Ω-L) keep the step-24 behaviour: admitted at once, unreserved; the guarantee covers only the
moments when no untyped job runs. **Off by default**: `fabric.Fabric` is unchanged, and `Scheduler(admit=False)` loads
every job at cycle 0, which is the step-24 multi-tenant behaviour. Step 25 had no RTL admission; step 26 adds it
behind a run-time knob (§7.5), so RTL defaults stay cycle-identical to step 24.

**Cost.** The rule gives every cell the whole of every reservation (it knows nothing about placement), and B_vars is
2.3–35× an RTL 1×1 run's var peak (§7.2), so on small cells it admits about one job at a time: the 180-job flood below takes 176,707
cycles admitted; a 120-job flood that the unadmitted fabric still survives takes 49,770 cycles without admission and
119,814 with it. Tests (`tests/test_s25.py`): 180 jobs of 15 owners on 2×2 × 280 slots and 300 on 3×3 × 280 stop
without admission (no progress, no tenant finishes) and finish with it (every answer right, every cycle audited:
live ≤ reserved, every cell keeps the margin); a never-admissible job (treesum(9), W_nodes 7,166) is rejected while
the others finish; a job that fits only alone waits for the others; an untyped qsort passes through.

### 7.5 Admission control in the RTL (step 26, `rtl/omega_adm.sv`, `omega/adm_rtl.py`)

§7.4's rule, in hardware. A small controller beside the mesh (`omega_adm`) and a host port on cell (0,0) replace
the Python scheduler's loader; nothing else in the mesh changes. **Run-time knob `+adm` (`adm_on`), default 0:**
with it off every controller output is idle, the host port is never driven and the orientation rule below is
inactive, so the mesh is the step-25 mesh cycle for cycle (identity 128 / 128).

**State.** A job table of NJ = 512 entries (owner, typed bit, reservation (n, v), the owner-stamped REF of the job's
`@main`), written by the host before the run like the definition ROM (`adm_info.hex`, `adm_ref.hex`); a config
block (job count, budget_n, budget_v = S − margin computed exactly as §7.4, root-pool base, margin); the FIFO head;
the running sums res_n, res_v of the running typed jobs' reservations; a 15-bit owner-busy vector; and a pool of
RR = 16 **root var slots** in cell (0,0) placed outside its free stacks (slots S .. S + 15, so every cell still has
exactly S allocatable slots, as in the model), each with a used / running bit, its job index and a shadow copy of
the slot (the controller watches cell (0,0)'s two var write ports).

**Start.** Each cycle with no action pending, the head job is

* **rejected** if it is typed and its reservation exceeds the budget on its own (it can never fit; §7.4's
  "rejected at submission", here when it reaches the head; the order of the other decisions is unchanged);
* **started** if its owner has no running job, a root slot is free and (typed) res + its reservation ≤ budget for
  nodes and vars alike, or (untyped) unconditionally (unreserved, as in §7.4);
* otherwise it waits (FIFO, no overtaking).

A start is two host-port actions on cell (0,0): (1) write {owner, NONE} into the chosen root slot, on var write
port 1 in a cycle the engine leaves it free; (2) offer the task {REF @main, VAR root}, which the cell takes as a
SPAWN at its next pick (the same path as a stack task, ahead of messages; expand here or hand on), so the cell's
own allocator places `@main` and the spawn / pressure policy decides where it expands. Like the static loader's
`@main`, the start is not an interaction.

**Root orientation rule** (only with `adm_on`): a var ~ var link never writes into a root var of the pool (the
other var takes the root instead). So a root slot only ever receives the job's final value, never a forwarding
pointer, and the shadow copy is the result.

**Completion** is detected at mesh quiescence (every cell idle for 2 cycles and no start pending): then no task,
message, retry slot or var-hop link of any owner exists, so every running job is done. The controller sweeps the
root slots (one per cycle): each running job is marked done, its owner freed, and when its result is an atom (NUM
/ ERA) its root slot is freed and its reservation released. A data result (a constructor) stays in the fabric (the
RTL has no host unload): its root slot stays used and, if typed, its reservation stays charged, so it is never
overwritten and the guarantee still holds. If the queue is not empty, nothing runs, the mesh is idle and the head
cannot start (no root slot, or reservations held by data results), the controller stops with an error (`blocked`)
instead of hanging.

**Guarantee.** The argument of §7.4 carries over unchanged: the controller admits exactly when the model's rule
does (same budget, same FIFO, same per-owner exclusion), tenants share no slots, and every typed job's live graph is
within its reservation, so while no untyped job runs the live graph is ≤ res ≤ budget and every cell keeps the
margin free. A simulation-only audit in the controller checks this every cycle (live nodes / vars from the cells'
free counters ≤ res while no untyped job runs or left data behind; res ≤ budget; on a mesh, every cell's free
node and var slots ≥ margin) and counts violations.

**Difference from the model.** The model detects completion per owner; the RTL only at global quiescence, so a job
that finished early keeps its reservation until the mesh is idle. On the test floods this costs nothing measurable
(the budget admits about one W-reserved job per batch anyway) and the decisions are identical (below); with many
small jobs and a large budget it would serialise batches. Per-owner idle detection (an owner-busy bit through the
mesh, routers included) is left open.

**Cross-check** (`tests/test_s26.py`): the RTL and `admission.Scheduler(dedupe=True)` (jobs with one source share
one copy of their definitions, as the ROM does) run the same job lists with the same budget and must agree on the
rejected set, the start order and the total interaction count (each job's count is schedule independent), every
admitted job must end with its known answer, no stall or blocked controller, zero audit violations, reservations
≤ budget, and no two jobs of one owner overlap in time. Without admission (`run_static`: every job loaded at cycle 0,
`+adm=0`) the same floods stop (status 3, no progress for 20,000 cycles).

### 7.6 Quicksort in Ω-L (step 27, `programs/qsort_l.olm`)

`programs/qsort.olm` stays outside Ω-L (rule A: `qs` uses the tail `t` twice, once per `filter`) and is unchanged.
`programs/qsort_l.olm` computes the same result with three rewrites:

* **one partition, a pair.** `part(p, xs)` walks the list once and returns `P(lo, hi)`; `qs` matches the pair once,
  so every list is used exactly once (affine). Elements `< p` go left, the rest (duplicates of the pivot included)
  right, as in `qsort.olm`.
* **structural `part` and `app`** (recursion on the list argument, rule R structural).
* **numeric fuel for `qs`.** `qs(n, xs)` recurses on `n − 1` (rule R numeric), started at `n = N`; since each
  recursive call gets a strictly shorter list than its parent, `len(xs) ≤ n` always holds, so the fuel never runs
  out before the list does (the `0` arm is never reached with a non-empty list on any input). The checker records
  `qs: numeric, ≤ 2^value unfolds`.

**Bounds.** B (§7.2) depends on the data (how many elements each partition moves, how much `app` copies). The
counted B is exact in closed form (§7.3) for two input families of the program's own template shape: descending
(the worst case) **B_nodes = 32·N² + 86·N + 17, B_vars = 59/2·N² + 141/2·N + 15** and ascending 43/2·N² + 193/2·N
+ 17 / 41/2·N² + 159/2·N + 15, exact on N = 0..40 with held-out N = 41, 42; the program's own pseudo-random input
gets an envelope only. A data decomposition (`results/s27/decomp.py`) is exact on every one of 133 literal and 130
program inputs:

    B_nodes = 35 + 118·N + 43·P + 21·A − 9·Z,   B_vars = 27 + 100·N + 41·P + 18·A − 6·Z

with P = elements moved by partitions (Σ over `qs` calls of the partitioned length), A = `app` steps, Z = `qs`
calls at fuel 0 (0 or 2). P ≤ N(N − 1)/2, A ≤ P, and Z = 2 only at the full chain, so with positive P and A
coefficients the maximum over every input of length N ≥ 1 is P = A = N(N − 1)/2, Z = 2: exactly the descending
closed form. **The worst-case envelope is attained and holds for every input**, not only the sampled ones. W (§7.3,
causal) is 3.6–6.9× below B_nodes and 2.0–2.5× below B_vars at N = 2..12, and above every semantic peak (5 orders).

**Cost.** qsort_l does fewer interactions than qsort (0.78× at N = 40: one pass per partition instead of two
filters) but is slower on a mesh (RTL 2×2: +36% cycles at N = 12, +32% at N = 30), because `part` returns its pair
only after the whole list was walked and `app` waits for the left half, so less work overlaps.

## 8. Termination detection

A cell is *idle* when its engine is in IDLE, its task stack is empty, its eject FIFO and outbox are
empty and all of its router input FIFOs are empty. Every flit is always held in exactly one of these
FIFOs, so "all cells idle" means no active pair and no in-flight message anywhere. The mesh ANDs the
idle bits (a quiescence tree), and the run ends after two consecutive all-idle cycles. Mutant 15
(ignore router FIFOs) shows that the check is needed. A larger chip would replace the combinational
AND tree with a pipelined tree or a Dijkstra–Safra token ring. Both preserve the same definition.

## 9. Verification hooks

`seed` (LFSR seeds for router arbitration, engine source selection and stall injection), `jitter`
(probability/256 that a link holds a flit for a cycle), `stall` (probability/256 that an idle engine
skips a cycle) and `pmsg` (message vs. task priority) give the RTL a different interleaving on every
run. Strong confluence makes any difference in the three observables a bug. `MUT` (512-bit parameter)
injects the mutations listed in `tests/mutants.py` (55 since step 23) (16–21: owner-capability checks; 27, 28, 39–41:
memory pressure and the retry slot, checked by `tests/test_mempress.py`).

## 10. Frontend (`omega/lang.py`)

Ω-lang has λ, application, `let`, `if`, `switch` (0 / predecessor), `match` on Scott-encoded `data`
types, 32-bit arithmetic and global recursive `def`s.
* **Compilation** follows the standard λ-calculus to interaction-combinator translation: λ is a CON
  binder, application is a CON with the argument and return, and `k` uses of a variable become a chain
  of `k-1` DUPs with one fresh label per binder (zero uses become ERA).
* **Arm lifting.** Interaction nets reduce under binders, so a recursive call inside an untaken branch
  would unfold forever. Any switch/match arm that could reduce on its own (it contains an application,
  a nested switch/match, or a reference) is lifted into its own closed definition. It stays a lazy
  `REF` until selected, and its free variables are passed as extra arguments. This is the Bend
  approach.
* **Patterns (step 6).** `match` arms take nested constructor patterns, numeric literals, variables and
  `_` (`Cons(a, Cons(b, t))`, `Cons(0, t)`, `P(T, T)`, `k => …`). A column-wise match compiler
  (`Desugar` in `omega/lang.py`) turns them into flat one-level Scott matches over every constructor,
  `==` tests for literals and defaults for binders, before arm lifting; the net-level encoding is
  unchanged. It rejects wrong constructor arity, unknown constructors, a binder used twice in one
  pattern, non-exhaustive matches, redundant arms and mixed pattern kinds.
* **Type checking (step 6).** `omega/typecheck.py`: Hindley–Milner inference with let-polymorphism and
  no annotations, generalised per strongly connected component of the call graph. Types are `Num`,
  each user data type (not parameterised; constructor fields get fresh types at every use), functions
  and type variables. It checks shapes: arithmetic, comparisons and `if` / `switch` conditions are
  numbers, `match` scrutinees have the matched data type, only functions are applied, arms agree, and
  `main` is a value. Errors are `SyntaxError` (scope, patterns) or `TypeError` (types), naming the
  definition.
* **Ω-L (step 24).** `omega/eal.py` checks the light-affine subset of §7.2 on top of these checks (monomorphic
  first-order constructor fields, affine non-number binders per emitted template, !-parameters fed inert
  closures, measure-decreasing recursion) and computes the compile-time peak-memory bound
  (`python3 -m omega.eal FILE.olm [--N n]`). The ordinary compiler does not require it.

## 11. Known gaps (MVP)

See README.md, "Known gaps".

## 12. Owner-capability isolation (multi-tenant fabric)

Several mutually distrusting programs (*tenants*) can share one fabric. Each tenant has an owner id
0..14 (15 = `OWN_FREE`, the tag of a free slot).

**Tags.** Every node slot and var slot carries a 4-bit shadow owner tag (`nown`, `vown`). The loader
tags every slot of tenant *k*'s image with its owner, and stamps the owner field `[43:40]` of every
*capability* port (VAR, REF, CON, DUP, OPR, SWI) it holds. NUM and ERA are values, not capabilities,
and always carry owner 0. Tenant *k*'s root var is cell (0,0), var slot *k*.

**Inheritance.** Every port and slot a rewrite creates takes the owner of the redex (the owner of its
capability side). An EXPAND stamps the owner of the REF port onto every port and slot it instantiates
(the ROM is shared by all tenants and its owner bits are ignored), one node write and one var-tag
write per cycle, i.e. `max(nn, nv)` cycles. Freeing a slot sets its tag to `OWN_FREE`. A program
therefore cannot choose the owner of any port; it can only forge the *address* bits (the `!var(x,y,s)`
IR atom, i.e. an `ABS` template port, models a program that fabricates a pointer).

**Checks (traps).** Checked in this order, in every model, at the cell that performs the access:

| trap | code | condition | where |
|---|---|---|---|
| CROSS | 1 | `link(a, b)` where a and b are both capabilities with different owners | every LINK step (sender before a LINK message leaves, receiver again on arrival); on NODE arrival (node vs partner) and SPAWN arrival (REF vs partner) |
| OOB | 3 | a VAR or node pointer outside the fabric: `x >= W`, `y >= H`, `slot >= SLOTS`, or non-zero address padding bits | before any local access *and* before a message is sent (so nothing is ever routed off the mesh) |
| FORGED | 2 | the owner tag of the addressed slot differs from the port's owner (includes free slots, tag 15) | var exchange at the var's home cell; node read (redex) at the node's home cell |

A trapped operation is **dropped** before it reads or writes anything: the victim's state is never
touched and no interaction is counted. The cell records the trap: a counter, the first trap's
`(reason, owner, address)` (the address names cell and slot), and a 48-bit mask of every
`(reason, owner)` pair seen; the testbench dumps them per cell. The offending owner's own graph may
be left incomplete; other tenants are unaffected. A CROSS trap blames the lower of the two owner ids.

**Why this is sound.** Owners come only from the loader and from stamping, never from program data.
Every write to a slot (var exchange, node creation, NODE re-homing) happens after T1/T2 (or creates a
slot tagged with the redex owner), so by induction every capability port stored in a tenant's slot
carries that tenant's owner, and any port with the right owner but a foreign address hits T2 or T3.
Strong confluence is preserved per tenant: tenants share no slots, so the honest tenants' normal forms,
live node counts and the total interaction count are schedule independent, and the set of
`(reason, owner)` traps is too (each dropped operation is dropped in every schedule).

**Fault injection.** The `fi[0]` knob makes the *sender* skip T1 whenever the access would leave the
cell, to show that the receiver-side checks (LINK, NODE, SPAWN arrival) and the slot tags still stop a
corrupted port that a faulty loader/DMA injected (tests re-stamp one of the attacker's initial ports
with the victim's owner). Under `fi` a corrupted access may be reported as FORGED rather than CROSS
and may count one REF expansion before the trap.

**Tests.** `tests/test_security.py`: two- and four-tenant program demos (each tenant gets its known
answer, zero traps), attacks (overwrite or capture the victim's result through a forged root-var
pointer, out-of-bounds slot / cell, forged node pointer to the victim's result node, an attack hidden
in a lazily expanded definition), the CROSS fault-injection cases with `fi` = 0 and 1, and a
multi-tenant random fuzz (2–4 random tenants with random owners, half of the cases with an attacker
carrying random forged redexes, random mesh, schedule knobs, scatter and `fi`). Mutants 16–21
disable each check in turn.

**Memory.** Isolation covers capabilities, not capacity: one tenant can still fill the shared memory. Step 25's
admission control (§7.4, fabric model) closes that for Ω-L jobs: a job starts only while the sum of the running
jobs' bounds fits every cell.
