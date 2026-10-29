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
  cell has **one non-LIFO retry slot** (`rs_v`, `rs_e`, a 32-cycle timer `rs_tm`, a park count
  `rs_n`): the retry is parked there, the engine keeps working on its stack and messages, and the
  parked entry is taken (before the stack) when its timer expires. A retry taken from the slot that has
  to park again counts up `rs_n`; on the 4th consecutive park the task **escalates**: a SPAWN is
  forwarded round robin (the old rule), a SWI node is sent as `NODE` and a commutation node as `PULL`
  to the next neighbour round robin even though it is not roomy. Escalation moves work across cells
  that are only partly full toward room several hops away (a roomy neighbour still always wins). The
  slot is single: a second retry while it is occupied takes the old path (stack / round robin), so no
  retry can be locked out of the slot forever. A parked entry keeps the cell non-idle and non-hungry
  (§8). Mutants 39–41 (parked entry never taken, quiescence ignoring the slot, no escalation).
  None of these change the result or the interaction count (migration is not an interaction), only
  where a rule runs. `tests/test_mempress.py` pre-fills cell (0,0) with foreign "ballast" so that only
  4–30 slots are free there: without the mechanism the v3 RTL livelocks on 7 of 30 such cases.
* **Task stack.** Depth-first (LIFO) order keeps live memory small (HVM2 uses per-thread stacks for the
  same reason). Retry tasks (`K_SPAWN`, re-queued `LINK`) reuse it.
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
    retries poll every 32 cycles instead of every cycle, but escalated SPAWNs (and SPAWNs that find the
    retry slot occupied) still bounce; `tests/test_mempress.py` checks that a globally full fabric ends
    in status 3 without a wrong answer.

  All are Known gaps (§11).

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
injects the 42 mutations listed in `tests/mutants.py` (16–21: owner-capability checks; 27, 28, 39–41:
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
