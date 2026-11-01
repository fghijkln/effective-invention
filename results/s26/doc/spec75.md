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
