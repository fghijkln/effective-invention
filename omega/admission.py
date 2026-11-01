"""Step 25: memory-bound admission control for a multi-tenant fabric (SPEC §7.4; fabric model only).

A *job* is a program with an owner id (SPEC §12).  An Ω-L job carries a compile-time bound (n, v) on its live node
and var count over every schedule: n = W_nodes (causal bound, step 24/25: sound wherever the live node count is
n0 + the deltas of a causally closed set of interactions, which holds for the semantic reducer, the fabric model and
the RTL because a node in flight holds no slot), v = B_vars (W_vars is a bound only for atomic links, see
omega/causal.py).  `bound="B"` uses (B_nodes, B_vars).

Admission rule (every cell has `slots` node and var slots):

    sum over running Ω-L jobs of n_j  <=  slots - margin       and the same for v_j,
    margin = 0 on one cell, D_max + max(LM_RSV, RSV) on a mesh (D_max: the largest template of the ROM).

Tenants share no slots, so the live graph of all running Ω-L jobs never exceeds sum n_j / sum v_j, no cell can
hold more than that, and every cell always keeps D_max + the reserve free: every expansion fits where it is and
every NODE / PULL finds a slot, the argument of §7.2 applied to the sum.  So the fabric can never reach the memory
stall of §7.1 (3) and no job can starve another of memory.  Jobs are admitted in arrival order (FIFO, no
overtaking): since Ω-L jobs terminate, a queued job waits only for jobs that finish.  A job whose bound exceeds the
empty fabric's budget is rejected at submission ("never admissible").  A job whose owner already has a running job
waits for it (one job per owner at a time, so completion can be told apart).

Untyped jobs (not in Ω-L) keep the step-24 behaviour: admitted at once, unreserved.  The guarantee above then
covers only the moments when no untyped job is running.

Completion of a job = its root var holds a value and no task, retry, var-hop link or message anywhere carries a
capability of its owner.  The scheduler then reads the result back, frees the job's remaining slots (a data result
is returned to the host) and releases its reservation.  Off by default: nothing here changes `fabric.Fabric`; with
`admit=False` all jobs are loaded at cycle 0, which is the step-24 multi-tenant behaviour.
"""
import os
from . import fabric, lang, ir, eal, causal, semantic
from .ports import *

MUT = eal.MUT        # OMEGA_EAL_MUT 11-13: admission mutants (tests/test_s25.py)


class Job:
    def __init__(self, name, src, owner, typed=None, bound="W"):
        self.name, self.src, self.owner = name, src, owner
        self.book = lang.compile_book(src)
        rep = eal.check(src) if typed is None or typed else {"ok": False, "reason": "declared untyped"}
        self.typed = rep["ok"]
        self.reason = rep.get("reason")
        self.res = None
        if self.typed:
            b = eal.bound(self.book)
            self.B = (b["B_nodes"], b["B_vars"])
            self.peak = (b["peak_nodes"], b["peak_vars"])
            if bound == "W":
                w = causal.bound(self.book, with_vars=False)
                self.need = (w["W_nodes"], b["B_vars"])
            else:
                self.need = self.B
            if MUT == 13: self.need = self.peak          # mutant 13: reserve the depth-first peak, not a bound
        else:
            self.B = self.need = self.peak = None
        self.state, self.t_submit, self.t_start, self.t_end, self.result = "new", None, None, None, None


class Scheduler:
    """Runs jobs on a fabric model.  admit=True: memory-bound admission; False: every job loaded at cycle 0."""

    def __init__(self, jobs, W, H, slots, admit=True, seed=1, stall=20000, max_cycles=2_000_000, **fab_kw):
        self.jobs, self.W, self.H, self.slots, self.admit = jobs, W, H, slots, admit
        self.book, mains = ir.merge_books([j.book for j in jobs])
        for j, m in zip(jobs, mains): j.main = m
        self.dmax = max(max(len(d.nodes), d.nvars) for d in self.book.defs)
        self.margin = 0 if W * H == 1 else self.dmax + max(fabric.LM_RSV, fabric.RSV)
        self.budget = (slots - self.margin, slots - self.margin)
        img = fabric.Image(self.book, W, H, slots, 1024, tenants=[{"owner": 0, "main": mains[0]}])
        for c in img.nodes:                              # an empty image: every job is loaded by load()
            img.nodes[c] = [None] * slots; img.vars[c] = [None] * slots
            img.nown[c] = [OWNER_FREE] * slots; img.vown[c] = [OWNER_FREE] * slots; img.queue[c] = []
        img.tenants, img.roots = [], []
        self.fab = fabric.Fabric(self.book, W, H, slots, seed=seed, img=img, **fab_kw)
        self.cells = [(x, y) for y in range(H) for x in range(W)]
        self.stall, self.max_cycles = stall, max_cycles
        self.queue, self.running, self.done = [], [], []
        self.reserved = [0, 0]
        self.loaded = 0
        self.events = []
        for j in jobs:
            j.t_submit = 0
            if admit and j.typed and (j.need[0] > self.budget[0] or j.need[1] > self.budget[1]):
                j.state = "rejected"; self.events.append((0, "reject", j.name)); continue
            self.queue.append(j)

    # ---------------------------------------------------------------------------------- loading
    def load(self, j):
        fab, o = self.fab, j.owner
        d = self.book[j.main]
        k = self.loaded; self.loaded += 1
        order = self.cells[k % len(self.cells):] + self.cells[:k % len(self.cells)]
        hc = fab.cells[order[0]]                         # root var in the home cell (the static Image: (0,0), slot k)
        if not hc.vfree: raise fabric.FabricError(f"job {j.name}: no var slot for its root var in cell {order[0]}")
        rs = hc.vfree.pop(); hc.vars[rs] = mk(NONE); hc.vown[rs] = o
        j.root = mk(VAR, 0, addr(order[0][0], order[0][1], rs), owner=o)

        def alloc(kind):
            for xy in order:
                c = fab.cells[xy]
                fl = c.nfree if kind == "n" else c.vfree
                if fl:
                    s = fl.pop()
                    if kind == "n": c.nodes[s] = [0, 0]; c.nown[s] = o
                    else: c.vars[s] = mk(NONE); c.vown[s] = o
                    return addr(xy[0], xy[1], s)
            raise fabric.FabricError(f"job {j.name}: @main does not fit")
        vmap = [alloc("v") for _ in range(d.nvars)]
        nmap = [alloc("n") for _ in range(len(d.nodes))]

        def tr(p):
            tg = tag(p)
            if p & ABS_BIT: return stamp(p, o)
            if tg == VAR: return mk(VAR, 0, vmap[payload(p)], owner=o)
            if tg in NODE_TAGS: return with_owner(with_payload(p, nmap[payload(p)]), o)
            return stamp(p, o)
        for i, (_, a, b) in enumerate(d.nodes):
            x, y = addr_xy(nmap[i])
            fab.cells[(x, y)].nodes[addr_slot(nmap[i])] = [tr(a), tr(b)]
        home = fab.cells[order[0]]
        for a, b in [(tr(d.root), j.root)] + [(tr(a), tr(b)) for a, b in d.redexes]:
            home.queue.append((fabric.T_LINK, a, b))
        j.state, j.t_start = "running", fab.cycles
        self.running.append(j)
        self.events.append((fab.cycles, "start", j.name))

    def try_admit(self):
        while self.queue:
            j = self.queue[0]
            if self.admit and any(r.owner == j.owner for r in self.running): break
            if self.admit and j.typed:
                fits = (self.reserved[0] + j.need[0] <= self.budget[0] and self.reserved[1] + j.need[1] <= self.budget[1])
                if MUT == 11: fits = j.need[0] <= self.budget[0] and j.need[1] <= self.budget[1]   # mutant 11: ignores running jobs
                if not fits: break
                self.reserved[0] += j.need[0]; self.reserved[1] += j.need[1]
            self.queue.pop(0)
            self.load(j)

    # ------------------------------------------------------------------------------- completion
    def busy_owners(self):
        """Owners with a pending task / retry / var-hop link / message anywhere (None: an item without capability)."""
        out = set()

        def mark(ports):
            for p in ports:
                if is_cap(p): out.add(owner(p))
        for c in self.fab.cells.values():
            for t in c.queue: mark(t[1:])
            if c.rs is not None: mark(c.rs[1:])
            if c.vh_out is not None: mark(c.vh_out)
            for q in list(c.inq.values()) + [c.eject]:
                for m in q: mark(m[3:])
        return out

    def finish(self, js):
        """Read the results of jobs js (one owner), then unload that owner's slots and release the reservations."""
        fab = self.fab
        o = js[0].owner
        nodes = {k: c.nodes for k, c in fab.cells.items()}
        vars_ = {k: c.vars for k, c in fab.cells.items()}
        for j in js:
            try:
                j.result = fabric.readback_dump(self.book, nodes, vars_, j.root)
            except Exception as e:
                j.result = f"ERROR {type(e).__name__}"
        for c in fab.cells.values():                    # unload: the results went to the host
            for i, t in enumerate(c.nown):
                if t == o: c.nodes[i] = None; c.nown[i] = OWNER_FREE; c.nfree.append(i)
            for i, t in enumerate(c.vown):
                if t == o: c.vars[i] = None; c.vown[i] = OWNER_FREE; c.vfree.append(i)
        for j in js:
            j.state, j.t_end = "done", fab.cycles
            self.running.remove(j); self.done.append(j)
            if self.admit and j.typed and MUT != 12:    # mutant 12: reservations never released
                self.reserved[0] -= j.need[0]; self.reserved[1] -= j.need[1]
            self.events.append((fab.cycles, "done", j.name))

    def check_done(self):
        """An owner with no pending work whose running jobs all have a value in their root var: all of them are done
        (without admission one owner may run several jobs at once; they finish together)."""
        if not self.running: return
        busy = self.busy_owners()
        for o in sorted({j.owner for j in self.running} - busy):
            js = [j for j in self.running if j.owner == o]
            if all(tag(self.fab.cells[addr_xy(payload(j.root))].vars[addr_slot(payload(j.root))]) != NONE for j in js):
                self.finish(js)

    # ---------------------------------------------------------------------------------------- run
    def audit_step(self):
        """The admission invariants (only while no untyped job runs): live nodes / vars of the running jobs <= the
        reservations, and on a mesh every cell keeps more than the margin free.  Returns a violation or None."""
        if not self.admit or any(not j.typed for j in self.running): return None
        ln = sum(len(c.nodes) - len(c.nfree) for c in self.fab.cells.values())
        lv = sum(len(c.vars) - len(c.vfree) for c in self.fab.cells.values())
        if ln > self.reserved[0] or lv > self.reserved[1]:
            return f"cycle {self.fab.cycles}: live {ln}/{lv} > reserved {self.reserved[0]}/{self.reserved[1]}"
        if self.margin:
            mf = min(min(len(c.nfree), len(c.vfree)) for c in self.fab.cells.values())
            if mf < self.margin: return f"cycle {self.fab.cycles}: a cell has only {mf} free slots (margin {self.margin})"
        return None

    def run(self, poll=16, audit=False):
        """Returns {"status": "ok" | "stall" | "error" | "cycles", ...}.  "stall": no interaction for `stall` cycles
        while jobs are unfinished (the model's out-of-memory / no-progress end, the RTL's status 3)."""
        fab = self.fab
        last, last_c, peak = -1, 0, [0, 0]
        status, err = "ok", None
        self.violation, self.max_reserved = None, [0, 0]
        try:
            self.try_admit()
            while self.running or self.queue:
                fab.step()
                if audit and self.violation is None: self.violation = self.audit_step()
                if fab.interactions != last: last, last_c = fab.interactions, fab.cycles
                if fab.cycles % 4 == 0:
                    ln = sum(len(c.nodes) - len(c.nfree) for c in fab.cells.values())
                    lv = sum(len(c.vars) - len(c.vfree) for c in fab.cells.values())
                    peak = [max(peak[0], ln), max(peak[1], lv)]
                if fab.cycles % poll == 0 or all(c.idle() for c in fab.cells.values()):
                    self.check_done(); self.try_admit()
                    self.max_reserved = [max(a, b) for a, b in zip(self.max_reserved, self.reserved)]
                if fab.cycles - last_c > self.stall:
                    status = "stall"; break
                if fab.cycles >= self.max_cycles:
                    status = "cycles"; break
                if not self.running and self.queue:           # nothing running, head cannot start: cannot happen
                    status = "blocked"; break
        except fabric.FabricError as e:
            status, err = "error", str(e)
        return {"status": status, "error": err, "violation": self.violation, "max_reserved": tuple(self.max_reserved),
                "budget": self.budget, "cycles": fab.cycles, "interactions": fab.interactions,
                "peak_live": tuple(peak), "events": self.events,
                "jobs": [{"name": j.name, "owner": j.owner, "typed": j.typed, "need": j.need, "state": j.state,
                          "result": j.result, "start": j.t_start, "end": j.t_end} for j in self.jobs]}
