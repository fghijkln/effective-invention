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
[43:40] owner   reserved for the owner-capability demo (always 0 in the MVP, see Known gaps)
[39:32] 0
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

### 2.4 Definition ROM (read-only templates, replicated in every cell)
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
          1024x128b     1024x64b      node / var       def ROM (templates) + dir
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
* **Task stack.** Depth-first (LIFO) order keeps live memory small (HVM2 uses per-thread stacks for the
  same reason). Retry tasks (`K_SPAWN`, re-queued `LINK`) reuse it.
* **Rule execution.** Reading both nodes, applying the rule, writing up to four node slots and
  launching the first resulting link take one cycle. Every further link costs one PUSH cycle, and is
  later popped as a task. The first link is processed immediately (tail-call), with no push.

### 5.1 Engine cost table (cycles, RTL)

| operation | cycles |
|---|---|
| pick a task or message (IDLE) | 1 |
| each link step (local var exchange, chain step, or remote send) | 1 |
| redex rule, including all node writes and the first resulting link | 1 (same LINK cycle) |
| each extra resulting link (annihilate/erase/copy: 1, commute: 3) | 1 |
| SPAWN decision (hungry-neighbour scan) | 1 |
| EXPAND: header + `nn` node writes + `nr` redex pushes + root link | 1 + nn + nr + 1 |
| router hop (FIFO to neighbour FIFO) | 1 per hop (+ jitter) |

The Python fabric model charges the same per-task costs. Its cycle counts are approximate (±20%),
because it does not model every FSM transition. Only the RTL numbers are reported as cycles.

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
    for 100000 cycles" and the RTL testbench with a cycle limit (status 3).

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
run. Strong confluence makes any difference in the three observables a bug. `MUT` (256-bit parameter)
injects the 16 mutations listed in `tests/mutants.py`.

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

## 11. Known gaps (MVP)

See README.md, "Known gaps".
