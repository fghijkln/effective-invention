"""Cycle-level model of the Spatial Interaction-Net Fabric (SPEC.md sections 5-8).

Every cell owns node RAM + var RAM (with allocation shadow tags), free stacks, a task queue,
a rewrite engine and a 5-port mesh router.  There is no global memory: cells only talk through
messages (LINK / NODE / SPAWN) carried hop by hop over the mesh.

The engine is modelled at task granularity: a task executes atomically and then keeps the engine
busy for the number of cycles the RTL FSM needs for it (cost table in SPEC.md 6.3).  Routers are
modelled flit-by-flit and cycle-by-cycle.  The RTL (rtl/) implements the same protocol; it is
checked against the *semantic* model (normal form + interaction count), not cycle-for-cycle
against this model.
"""
import random
from collections import deque
from .ports import *
from . import semantic

MSG_LINK, MSG_NODE, MSG_SPAWN, MSG_PULL = 0, 1, 2, 3
SPAWN_K = int(__import__('os').environ.get('OMEGA_SPAWN_K', '16'))
SPAWN_HINT = int(__import__('os').environ.get('OMEGA_SPAWN_HINT', '1'))
SPAWN_K2 = int(__import__('os').environ.get('OMEGA_SPAWN_K2', '4'))
LINK_LOCAL = int(__import__('os').environ.get('OMEGA_LINK_LOCAL', '1'))
# step 13 adaptive spawn (SPEC 5.2): (mode, K_lo, K_hi, init); mode 0 = step-12 static thresholds,
# 1 = receiver-measured data affinity (2-bit counter per definition, advertised to the neighbours)
GRAN = tuple(int(v) for v in __import__('os').environ.get('OMEGA_GRAN', '0,4,0,1').split(','))
GT_N = 32         # per-cell granularity table entries (2-bit counters, indexed by definition id mod 32)
MSG_NAMES = ["LINK", "NODE", "SPAWN", "PULL"]
T_LINK, T_EXPAND, T_SPAWN, T_FWD = 0, 1, 2, 3
RTO = 32          # retry-slot timeout (cycles), as rtl/omega_cell.sv
DIRS = ["N", "E", "S", "W"]
DXY = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0)}
OPP = {"N": "S", "S": "N", "E": "W", "W": "E"}


class FabricError(Exception):
    pass


XMAP = 64      # RTL expansion maps: at most 64 nodes and 64 vars per definition


# ---------------------------------------------------------------------------------------------
# Loader: memory image (shared with the RTL testbench)
# ---------------------------------------------------------------------------------------------
class Image:
    """Initial distribution of the tenants' @main nets over the cells + book ROM.

    tenants: list of {"owner": o, "main": def id, "patch": fn(links)->links (fault injection)}; default
    one tenant, owner 0, @main.  Tenant k's root var = cell(0,0) var slot k.  Every capability port a
    tenant's image holds is stamped with its owner, and every slot it occupies gets that owner's
    shadow tag; free slots carry OWNER_FREE."""

    def __init__(self, book, W, H, slots=1024, qdepth=1024, main_cells=None, scatter=None, tenants=None):
        self.book, self.W, self.H, self.slots, self.qdepth = book, W, H, slots, qdepth
        self.tenants = tenants or [{"owner": 0, "main": book.id("main")}]
        T = len(self.tenants)
        self.nodes = {(x, y): [None] * slots for x in range(W) for y in range(H)}
        self.vars = {(x, y): [None] * slots for x in range(W) for y in range(H)}
        self.nown = {(x, y): [OWNER_FREE] * slots for x in range(W) for y in range(H)}
        self.vown = {(x, y): [OWNER_FREE] * slots for x in range(W) for y in range(H)}
        self.queue = {(x, y): [] for x in range(W) for y in range(H)}
        self.roots = []
        for k, t in enumerate(self.tenants):
            if not 0 <= t["owner"] < OWNER_FREE:
                raise FabricError("owner ids are 0..14")
            self.vars[(0, 0)][k] = mk(NONE)
            self.vown[(0, 0)][k] = t["owner"]
            self.roots.append(mk(VAR, 0, addr(0, 0, k), owner=t["owner"]))
        self.root = self.roots[0]
        cells = [(x, y) for y in range(H) for x in range(W)]
        srng = random.Random(scatter) if scatter is not None else None
        for k, t in enumerate(self.tenants):
            o = t["owner"]
            order = main_cells or (cells[k % len(cells):] + cells[:k % len(cells)])
            d = book[t["main"]]

            def alloc(kind):
                seq = order
                if srng is not None:
                    seq = order[:]
                    srng.shuffle(seq)
                for c in seq:
                    tab = self.nodes[c] if kind == "n" else self.vars[c]
                    for s in range(slots):
                        if tab[s] is None:
                            tab[s] = mk(NONE) if kind == "v" else [0, 0]
                            (self.nown if kind == "n" else self.vown)[c][s] = o
                            return addr(c[0], c[1], s)
                raise FabricError("@main does not fit in the fabric")
            vmap = [alloc("v") for _ in range(d.nvars)]
            nmap = [alloc("n") for _ in range(len(d.nodes))]

            def tr(p):
                tg = tag(p)
                if p & ABS_BIT: return stamp(p, o)
                if tg == VAR: return mk(VAR, 0, vmap[payload(p)], owner=o)
                if tg in NODE_TAGS: return with_owner(with_payload(p, nmap[payload(p)]), o)
                return stamp(p, o)
            for j, (_, a, b) in enumerate(d.nodes):
                x, y = addr_xy(nmap[j])
                self.nodes[(x, y)][addr_slot(nmap[j])] = [tr(a), tr(b)]
            links = [(tr(d.root), self.roots[k])] + [(tr(a), tr(b)) for a, b in d.redexes]
            if t.get("patch"):
                links = t["patch"](links)
            home = order[0] if srng is None else (0, 0)
            for a, b in links:
                self.queue[home].append((T_LINK, a, b))
        # book ROM: dir[id] = entry index of header; header = (root, counts); then nodes, then redexes
        self.rom = []
        self.dir = []
        self.romn, self.romr, self.dir3 = [], [], []
        self.fork, self.rec, self.prod = fork, rec, prod = fork_defs(book, with_prod=True)
        for dd in book.defs:
            self.dir.append(len(self.rom))
            cnt = len(dd.nodes) | (dd.nvars << 8) | (len(dd.redexes) << 16)
            if len(dd.nodes) > XMAP or dd.nvars > XMAP or len(dd.redexes) > 255:
                raise FabricError(f"definition @{dd.name} too large for one EXPAND "
                                  f"({len(dd.nodes)} nodes / {dd.nvars} vars, limit {XMAP})")
            self.rom.append((dd.root, cnt))
            self.dir3.append(len(self.romn) | (len(self.romr) << 16) | (cnt << 32) | (int(len(self.dir3) in fork) << 56) | (int(len(self.dir3) in rec) << 57) | (int(len(self.dir3) in prod) << 58) | (dd.root << 64))
            self.romn += [(a, b) for (_, a, b) in dd.nodes]
            self.romr += list(dd.redexes)
            # cluster ROM words hold four entries: align every definition to a multiple of four
            while len(self.romn) % 4: self.romn.append((0, 0))
            while len(self.romr) % 4: self.romr.append((0, 0))
            for (_, a, b) in dd.nodes:
                self.rom.append((a, b))
            for a, b in dd.redexes:
                self.rom.append((a, b))

    def write_hex(self, outdir):
        """Files consumed by rtl/omega_cell.sv ($readmemh)."""
        import os
        os.makedirs(outdir, exist_ok=True)
        h = lambda v, w: format(v, "0%dx" % w)
        for (x, y), tab in self.nodes.items():
            with open(f"{outdir}/node_{x}_{y}.hex", "w") as f:
                for e, o in zip(tab, self.nown[(x, y)]):
                    f.write(h((o << 128) | (0 if e is None else (e[1] << 64) | e[0]), 33) + "\n")
            with open(f"{outdir}/nalloc_{x}_{y}.hex", "w") as f:
                for e in tab:
                    f.write("0\n" if e is None else "1\n")
            with open(f"{outdir}/var_{x}_{y}.hex", "w") as f:
                for e, o in zip(self.vars[(x, y)], self.vown[(x, y)]):
                    f.write(h((o << 64) | (0 if e is None else e), 17) + "\n")
            with open(f"{outdir}/valloc_{x}_{y}.hex", "w") as f:
                for e in self.vars[(x, y)]:
                    f.write("0\n" if e is None else "1\n")
            with open(f"{outdir}/nown_{x}_{y}.hex", "w") as f:
                f.write("".join("%x\n" % o for o in self.nown[(x, y)]))
            with open(f"{outdir}/vown_{x}_{y}.hex", "w") as f:
                f.write("".join("%x\n" % o for o in self.vown[(x, y)]))
            q = self.queue[(x, y)]
            if len(q) > self.qdepth:
                raise FabricError("initial queue too long")
            with open(f"{outdir}/queue_{x}_{y}.hex", "w") as f:
                for i in range(self.qdepth):
                    k, a, b = q[i] if i < len(q) else (0, 0, 0)
                    f.write(h((k << 128) | (b << 64) | a, 33) + "\n")
            with open(f"{outdir}/qcount_{x}_{y}.hex", "w") as f:
                f.write(h(len(q), 4) + "\n")
        with open(f"{outdir}/rom.hex", "w") as f:
            for a, b in self.rom:
                f.write(h((b << 64) | a, 32) + "\n")
        # v3 cell: node template ROM, redex template ROM, directory {root, nr, nv, nn, rbase, nbase}
        # cluster ROM (rtl/omega_rom.sv): one 512-bit word = entries 4k (bits 127:0) .. 4k + 3
        for nm, tab in (("romn", self.romn), ("romr", self.romr or [(0, 0)] * 4)):
            with open(f"{outdir}/{nm}.hex", "w") as f:
                for k in range(0, len(tab), 4):
                    w = 0
                    for j in range(4):
                        a, b = tab[k + j]
                        w |= ((b << 64) | a) << (128 * j)
                    f.write(h(w, 128) + "\n")
        with open(f"{outdir}/dir.hex", "w") as f:
            for d in self.dir3:
                f.write(h(d, 32) + "\n")
        with open(f"{outdir}/rom_size.txt", "w") as f:
            f.write(f"{len(self.rom)} {len(self.dir)}\n")


def readback_dump(book, nodes, vars_, root=mk(VAR, 0, addr(0, 0, 0))):
    """nodes/vars_: dict (x,y) -> list.  Returns canonical readback text."""
    def gn(p):
        a = payload(p); x, y = addr_xy(a)
        e = nodes[(x, y)][addr_slot(a)]
        if e is None:
            raise FabricError(f"dangling node pointer {show_port(p)}")
        return e

    def gv(p):
        a = payload(p); x, y = addr_xy(a)
        e = vars_[(x, y)][addr_slot(a)]
        return mk(NONE) if e is None else e
    return semantic.readback(gn, gv, root, book)


def fork_defs(book, with_rec=False, with_prod=False):
    """Step 11 spawn hint (SPEC 5): the definitions worth handing to another cell.  A definition is a
    fork target when it belongs to a recursion SCC that some template calls at least twice (both
    branches of a divide-and-conquer recursion, e.g. fib(n-1) and fib(n-2), qs(lo) and qs(hi); the two
    arms of a switch count once); its REF expansions are the coarse-grained work.  REFs into a linear recursion (a list walk, a filter
    chain, a counter) are expanded where they meet their partner, so a sequential chain does not hop
    from cell to cell dragging remote wires behind it.  Returns a set of definition ids."""
    n = len(book.defs)
    calls, groups = [], []          # calls: every REF (call graph); groups: alternatives grouped
    for d in book.defs:
        # the two branches of a switch, ?((A B) r), are alternatives, not two calls: a SWI node's aux1
        # (a CON pair) counts as one group
        alt = set()
        for (tp, a, b) in d.nodes:
            if tag(tp) == SWI and tag(a) == CON and not (a & ABS_BIT):
                alt.add(payload(a))
        refs, grp = [], []
        for j, (tp, a, b) in enumerate(d.nodes):
            ps = [label(p) for p in (a, b) if tag(p) == REF and not (p & ABS_BIT)]
            refs += ps
            grp += [ps] if j in alt and ps else [[q] for q in ps]
        for p in [d.root] + [q for r in d.redexes for q in r]:
            if p is not None and tag(p) == REF and not (p & ABS_BIT):
                refs.append(label(p)); grp.append([label(p)])
        calls.append(refs); groups.append(grp)
    # SCCs (Tarjan, iterative enough for small books)
    idx, low, onst, st, comp, k = {}, {}, set(), [], [0] * n, [0]
    def strong(v):
        idx[v] = low[v] = k[0]; k[0] += 1; st.append(v); onst.add(v)
        for w in set(calls[v]):
            if w >= n: continue
            if w not in idx:
                strong(w); low[v] = min(low[v], low[w])
            elif w in onst:
                low[v] = min(low[v], idx[w])
        if low[v] == idx[v]:
            while True:
                w = st.pop(); onst.discard(w); comp[w] = v
                if w == v: break
    import sys as _s
    _s.setrecursionlimit(max(_s.getrecursionlimit(), 10000))
    for v in range(n):
        if v not in idx: strong(v)
    rec = {u for u in range(n) if sum(comp[w] == comp[u] for w in range(n)) > 1 or u in calls[u]}
    fork = set()
    for v in range(n):
        for c in set(comp[w] for w in calls[v] if w < n):
            hits = [g for g in groups[v] if any(w < n and comp[w] == c for w in g)]
            if len(hits) >= 2 and c in rec:
                fork.update(u for u in range(n) if comp[u] == c)     # the whole recursion SCC
    # step 13: a linear recursion is a *producer* when a template of its SCC calls a non-recursive
    # definition outside the SCC (a constructor such as Cons / Nil / Leaf): it emits a data structure
    # piece by piece, so the consumer can work on the head while the tail is still being made
    # (pipeline parallelism, and the data ends up spread over the cells that produced it).  A strict
    # recursion (sum, fact, a fold into an operator) only feeds its own pending operators.
    prod = set()
    for u in rec - fork:
        cu = comp[u]
        scc = [v for v in range(n) if comp[v] == cu]
        if any(w < n and comp[w] != cu and w not in rec for v in scc for w in calls[v]):
            prod.add(u)
    if with_prod:
        return fork, rec, prod
    return (fork, rec) if with_rec else fork


# ---------------------------------------------------------------------------------------------
# Cycle model
# ---------------------------------------------------------------------------------------------
class Cell:
    def __init__(self, fab, x, y, img):
        self.fab, self.x, self.y = fab, x, y
        self.nodes = [None if e is None else list(e) for e in img.nodes[(x, y)]]
        self.vars = list(img.vars[(x, y)])
        self.nown = list(img.nown[(x, y)])
        self.vown = list(img.vown[(x, y)])
        self.traps = []
        self.nfree = [s for s in range(img.slots - 1, -1, -1) if self.nodes[s] is None]
        self.vfree = [s for s in range(img.slots - 1, -1, -1) if self.vars[s] is None]
        self.queue = deque(img.queue[(x, y)])
        self.inq = {d: deque() for d in DIRS + ["L"]}     # router input FIFOs (L = local outbox)
        self.eject = deque()
        self.busy = 0
        self.rr = 0
        # single non-LIFO retry slot (step 10, SPEC 9.1): (kind, a, b), timeout, park count
        self.rs, self.rs_tm, self.rs_n, self.cur_rs, self.cur_rsn = None, 0, 0, False, 0
        self.nbrs = [d for d in ("E", "S", "W", "N")
                     if 0 <= x + DXY[d][0] < fab.W and 0 <= y + DXY[d][1] < fab.H]
        self.spawn_targets = [None] + self.nbrs
        # memory pressure (SPEC 9): roomy = free node and var slots above a watermark, with hysteresis
        self.room_hi, self.room_lo = img.slots // 4, img.slots // 8
        self._roomy = False
        self.update_roomy()
        self.st = {"interactions": 0, "busy": 0, "tasks": 0, "msgs_in": 0, "requeue": 0, "max_q": len(self.queue),
                   "max_nodes": 0, "vhu": 0}
        # var-hop unit (RTL step 9): follows substitution chains in parallel with the engine
        self.vh_busy, self.vh_out = 0, None
        # step 13 granularity table + the job (received SPAWN) being measured
        self.gt = [fab.gran[3]] * GT_N
        self.born = [None] * img.slots   # table index of the received SPAWN job that created the node
        self.job = None                  # table index while expanding a received SPAWN
        self.node_in = False             # the current link comes from a NODE message (a consumer arrived)
        self.ep_m, self.ep_i = 0, 0      # message-budget governor: messages / interactions this epoch
        self.lvl = fab.gran[3] if fab.gran[0] == 3 else 0

    # ---- helpers ----
    def local(self, p):
        return addr_xy(payload(p)) == (self.x, self.y)

    def can_send(self):
        return len(self.inq["L"]) < self.fab.fifo_depth

    def send(self, kind, dst, *pl):
        assert self.can_send()
        self.inq["L"].append((kind, dst[0], dst[1]) + pl)
        self.fab.msgs[kind] += 1
        self.ep_m += 1

    def send_or_retry(self, kind, dst, a, b):
        """LINK / SPAWN sends never block the engine: if the outbox is full the work goes back to the
        local task stack as a retry task (SPEC 7: the engine always drains its ejection port)."""
        if self.can_send():
            self.send(kind, dst, a, b)
        else:
            self.queue.append((T_LINK if kind == MSG_LINK else T_SPAWN, a, b))
            self.st["retry"] = self.st.get("retry", 0) + 1

    def push(self, a, b):
        self.queue.append((T_LINK, a, b))

    def free_node(self, p):
        s = addr_slot(payload(p))
        e = self.nodes[s]
        self.born[s] = None
        self.nodes[s] = None
        self.nown[s] = OWNER_FREE
        self.nfree.append(s)
        return e

    # ---- owner-capability checks (SPEC 12) ----
    def trap(self, reason, p):
        self.traps.append((reason, owner(p), payload(p)))
        return 0

    def oob(self, p):
        a = payload(p); x, y = addr_xy(a)
        return x >= self.fab.W or y >= self.fab.H or addr_slot(a) >= self.fab.slots or (a & 0xFF00F000) != 0

    def cross(self, a, b, remote=False):
        """T1.  With fault injection fi_nosend the sender skips it, so the receiver must catch it."""
        if remote and self.fab.fi_nosend:
            return False
        return is_cap(a) and is_cap(b) and owner(a) != owner(b)

    def forged_node(self, p):
        return self.nown[addr_slot(payload(p))] != owner(p)

    def here(self, slot):
        return addr(self.x, self.y, slot)

    def nbr_xy(self, d):
        return self.x + DXY[d][0], self.y + DXY[d][1]

    def count(self):
        self.st["interactions"] += 1
        self.fab.interactions += 1
        if self.fab.gran[0] == 3:
            self.ep_i += 1
            if self.ep_i == self.fab.gran[2]:
                # epoch end: over budget -> tighten the producer threshold, well under -> relax it
                b = self.fab.gran[1] * self.ep_i
                if 100 * self.ep_m > b: self.lvl = min(4, self.lvl + 1)
                elif 200 * self.ep_m < b: self.lvl = max(0, self.lvl - 1)
                self.ep_m = self.ep_i = 0

    # ---- link (SPEC 4) ----
    def do_link(self, a, b):
        cost = 0
        while True:
            cost += 1
            if not is_var(a) and is_var(b):
                a, b = b, a
            if self.fab.link_local and self.flip(a, b):
                a, b = b, a
            if self.cross(a, b, self.fab.fi_nosend and self.remote_target(a, b)):
                return cost + self.trap(TRAP_CROSS, a if owner(a) < owner(b) else b)
            if not is_var(a):
                return cost + self.redex(a, b)
            if self.oob(a):
                return cost + self.trap(TRAP_OOB, a)
            if not self.local(a):
                self.send_or_retry(MSG_LINK, addr_xy(payload(a)), a, b)
                return cost
            s = addr_slot(payload(a))
            if self.vown[s] != owner(a):
                return cost + self.trap(TRAP_FORGED, a)
            old = self.vars[s]
            if old is None:
                raise FabricError(f"link into free var {show_port(a)} at {self.x},{self.y}")
            if tag(old) == NONE:
                self.vars[s] = b
                return cost
            self.vars[s] = None
            self.vown[s] = OWNER_FREE
            self.vfree.append(s)
            a = old

    def vhu_chain(self, a, b):
        """Var-hop unit: exchanges while the link has a local, correctly tagged var on one side and no
        cross-owner check fails.  Returns (exchanges, link handed back to the engine or None)."""
        hops = 0
        while True:
            if not is_var(a) and is_var(b):
                a, b = b, a
            if self.fab.link_local and self.flip(a, b):
                a, b = b, a
            if (not is_var(a) or self.oob(a) or not self.local(a) or self.cross(a, b)
                    or self.vown[addr_slot(payload(a))] != owner(a)):
                return hops, ((a, b) if hops else None)
            s = addr_slot(payload(a))
            hops += 1
            old = self.vars[s]
            if tag(old) == NONE:
                self.vars[s] = b
                return hops, None
            self.vars[s] = None
            self.vown[s] = OWNER_FREE
            self.vfree.append(s)
            a = old

    def flip(self, a, b):
        """Step 12 local-first link orientation (SPEC 4): a link between two vars may be resolved at
        either var's owner (link is symmetric).  When A is a remote var and B a local, in-bounds var,
        exchange at B here instead of sending LINK(A ~ B) to A's cell."""
        return is_var(a) and is_var(b) and not self.oob(a) and not self.local(a) and not self.oob(b) and self.local(b)

    def remote_target(self, a, b):
        """Would this link/redex leave the cell (used only by the fault-injection knob)?"""
        if is_var(a):
            return self.oob(a) or not self.local(a)
        return any(is_node(p) and (self.oob(p) or not self.local(p)) for p in (a, b))

    def update_roomy(self):
        nf, vf = len(self.nfree), len(self.vfree)
        if nf >= self.room_hi and vf >= self.room_hi:
            self._roomy = True
        elif nf < self.room_lo or vf < self.room_lo:
            self._roomy = False

    def roomy(self):
        return self._roomy

    def hungry(self):
        return self._roomy and not (self.busy or self.queue or self.eject or self.vh_busy or self.vh_out or self.rs)

    def escalated(self):
        """The current task is a retry parked 4 times in a row: fall back to round-robin moves."""
        return bool(self.nbrs) and self.cur_rs and self.cur_rsn == 3

    def park(self, kind, a, b):
        """Memory-pressure retry: park in the single retry slot for RTO cycles (False if it is full)."""
        if self.rs is not None:
            return False
        self.rs, self.rs_tm = (kind, a, b), RTO
        self.rs_n = min(self.cur_rsn + 1, 3) if self.cur_rs else 0
        self.st["park"] = self.st.get("park", 0) + 1
        return True

    def roomy_nbr(self):
        """First roomy neighbour in rotating order (N E S W), or None."""
        self.mrot = getattr(self, "mrot", self.x + self.y) + 1
        order = ["N", "E", "S", "W"]
        for k in range(4):
            d = order[(self.mrot + k) % 4]
            if d in self.nbrs and self.fab.cells[self.nbr_xy(d)].roomy():
                return d
        return None

    def give(self, r, nb=None):
        """Step 11 sender-side decision (SPEC 5): fork targets always (with the hint); a definition of a
        linear recursion only while more than spawn_k tasks wait here; a non-recursive one (constructor,
        arm) while more than spawn_k2 wait.  K = -1: no threshold.  Without the hint every REF uses spawn_k."""
        q, fab = len(self.queue), self.fab
        if not fab.spawn_hint:
            return q > fab.spawn_k
        if r in fab.img.fork:
            return True
        k = fab.spawn_k if r in fab.img.rec else fab.spawn_k2
        if fab.gran[0] == 3:
            if r in fab.img.prod:
                k = (0, 2, 4, 8, 16)[self.lvl]
        elif fab.gran[0] == 2:
            if r in fab.img.prod:
                k = fab.gran[1] if k < 0 else min(k, fab.gran[1])
        elif fab.gran[0] and nb is not None:
            c = nb.gt[r % GT_N]           # the receiver's own verdict on jobs of this definition
            if c >= 2:
                k = fab.gran[1] if k < 0 else min(k, fab.gran[1])
            elif c == 0 and k >= 0:
                k = max(k, fab.gran[2])
        return q > k

    def gran(self, p, up):
        """Step 13: node p (local) was created by a received SPAWN job of definition i: a consumer that
        migrated here and meets it is a credit (the job placed data where work comes to it); the node
        itself migrating away is a debit (the job's work went back where it came from)."""
        i = self.born[addr_slot(payload(p))]
        if i is not None:
            self.gt[i] = min(3, self.gt[i] + 1) if up else max(0, self.gt[i] - 1)

    def spawn(self, ref, x):
        """Demand-driven work distribution: hand the expansion to a hungry neighbour (one that
        advertises an empty task stack on its side-band wire), otherwise expand locally."""
        self.hrot = (getattr(self, "hrot", self.x + self.y)) + 1
        order = ["N", "E", "S", "W"]
        for k in range(4):
            d = order[(self.hrot - 1 + k) % 4]
            if (d in self.nbrs and self.give(label(ref), self.fab.cells[self.nbr_xy(d)])
                    and self.fab.cells[self.nbr_xy(d)].hungry() and self.can_send()):
                self.send(MSG_SPAWN, self.nbr_xy(d), ref, x)
                return 1
        return self.expand(ref, x)

    def expand(self, refp, x, forwarded=False):
        """refp: the REF port (its owner stamps everything the expansion creates)."""
        ref, o = label(refp), owner(refp)
        d = self.fab.book[ref]
        nn, nv = len(d.nodes), d.nvars
        if len(self.nfree) < nn or len(self.vfree) < nv:
            if self.nbrs:
                t = self.roomy_nbr()          # out of memory: prefer a roomy neighbour
                if t is None and not self.escalated() and self.park(T_SPAWN, refp, x):
                    self.st["requeue"] += 1   # no roomy neighbour: park (forwarded after 4 parks)
                    return 1
                if t is None:
                    t = self.nbrs[self.rr % len(self.nbrs)]
                    self.rr += 1
                self.send_or_retry(MSG_SPAWN, self.nbr_xy(t), refp, x)
                self.st["requeue"] += 1
                return 1
            raise FabricError("out of memory (1x1 fabric cannot place expansion)")
        nmap = [self.nfree[-1 - j] for j in range(nn)]
        vmap = [self.vfree[-1 - i] for i in range(nv)]
        del self.nfree[len(self.nfree) - nn:]
        del self.vfree[len(self.vfree) - nv:]
        for s in vmap:
            self.vars[s] = mk(NONE)
            self.vown[s] = o

        def tr(p):
            t = tag(p)
            if p & ABS_BIT: return stamp(p, o)
            if t == VAR: return mk(VAR, 0, self.here(vmap[payload(p)]), owner=o)
            if t in NODE_TAGS: return with_owner(with_payload(p, self.here(nmap[payload(p)])), o)
            return stamp(p, o)
        for j, (_, a, b) in enumerate(d.nodes):
            self.nodes[nmap[j]] = [tr(a), tr(b)]
            self.nown[nmap[j]] = o
            self.born[nmap[j]] = self.job
        self.push(tr(d.root), x)
        for a, b in d.redexes:
            self.push(tr(a), tr(b))
        # v4 RTL: two entries (node, var tag, redex) per cycle, allocation alongside; one ROM word = 4 entries
        return 1 + (max(nn, nv, len(d.redexes)) + 1) // 2 + self.fab.rom_wait(self, (max(nn, len(d.redexes)) + 3) // 4)

    # ---- redex (SPEC 3, 6) ----
    def redex(self, a, b):
        ta, tb = tag(a), tag(b)
        if ta < tb or (ta == tb and label(a) < label(b)):
            a, b, ta, tb = b, a, tb, ta
        if ta <= NUM:
            self.count()
            if tb == REF and ta != ERA:
                return self.spawn(b, a)
            return 0
        if tb <= NUM:
            if tb == REF and ta != DUP:
                self.count()
                return self.spawn(b, a)
            if self.oob(a):
                return self.trap(TRAP_OOB, a)
            if not self.local(a):
                self.send_or_retry(MSG_LINK, addr_xy(payload(a)), a, b)
                return 0
            if self.forged_node(a):
                return self.trap(TRAP_FORGED, a)
            if ta == SWI and tb == NUM and payload(b) != 0 and not self.nfree:
                d = self.roomy_nbr() if self.can_send() else None
                if d is None and self.escalated() and self.can_send():
                    d = self.nbrs[self.rr % len(self.nbrs)]; self.rr += 1   # escalated retry: round robin
                if d is not None:             # no slot: move the SWI node to a roomy neighbour
                    a1, a2 = self.free_node(a)
                    self.send(MSG_NODE, self.nbr_xy(d), a, a1, a2, b)
                    self.st["offload"] = self.st.get("offload", 0) + 1
                    return 1
                if not self.park(T_LINK, a, b):
                    self.queue.append((T_LINK, a, b))
                self.st["requeue"] += 1
                return 0
            self.count()
            o = owner(a)
            sa = addr_slot(payload(a))
            a1, a2 = self.free_node(a)
            if tb in (ERA, REF) or ta in (CON, DUP):
                self.push(a1, b); self.push(a2, b)
                return 1 + 2
            x = payload(b)
            if ta == OPR:
                l = label(a); op, s = l & 15, l >> 4
                if tag(a1) == NUM:
                    y = payload(a1)
                    self.push(a2, num(apply_op(op, y, x) if s else apply_op(op, x, y)))
                else:
                    m = self.nfree.pop()           # == sa (slot reuse)
                    self.nodes[m] = [b, a2]; self.nown[m] = o
                    self.push(a1, mk(OPR, op | ((1 - s) << 4), self.here(m), owner=o))
                return 1 + 1
            # SWI
            if x == 0:
                c = self.nfree.pop()
                self.nodes[c] = [a2, ERA_P]; self.nown[c] = o
                self.push(a1, mk(CON, 0, self.here(c), owner=o))
            else:
                c1 = self.nfree.pop()
                c2 = self.nfree.pop()
                self.nodes[c1] = [num(x - 1), a2]; self.nown[c1] = o
                self.nodes[c2] = [ERA_P, mk(CON, 0, self.here(c1), owner=o)]; self.nown[c2] = o
                self.push(a1, mk(CON, 0, self.here(c2), owner=o))
            return 1 + 1
        if self.oob(a):
            return self.trap(TRAP_OOB, a)
        if self.oob(b):
            return self.trap(TRAP_OOB, b)
        la, lb = self.local(a), self.local(b)
        if la and self.forged_node(a):
            return self.trap(TRAP_FORGED, a)
        if lb and self.forged_node(b):
            return self.trap(TRAP_FORGED, b)
        if la and lb:
            anni = ta == tb and label(a) == label(b) and ta in (CON, DUP)
            if not anni and (len(self.nfree) < 2 or len(self.vfree) < 4):
                d = self.roomy_nbr() if self.can_send() else None
                if d is None and self.escalated() and self.can_send():
                    d = self.nbrs[self.rr % len(self.nbrs)]; self.rr += 1   # escalated retry: round robin
                if d is not None:
                    # no room for the commutation: PULL protocol, the roomy neighbour re-homes P and
                    # asks for Q (which then migrates with the ordinary NODE rule); poor -> rich
                    a1, a2 = self.free_node(a)
                    self.send(MSG_PULL, self.nbr_xy(d), a, a1, a2, b)
                    self.st["offload"] = self.st.get("offload", 0) + 1
                    return 1
                if not self.park(T_LINK, a, b):
                    self.queue.append((T_LINK, a, b))
                self.st["requeue"] += 1
                return 0
            self.count()
            if self.node_in and self.fab.gran[0]:
                self.gran(a, True); self.gran(b, True)
            a1, a2 = self.free_node(a)
            b1, b2 = self.free_node(b)
            if anni:
                self.push(a1, b1); self.push(a2, b2)
                return 1 + 2
            o = owner(a)
            v = [self.vfree.pop() for _ in range(4)]
            for s in v:
                self.vars[s] = mk(NONE); self.vown[s] = o
            x11, x12, x21, x22 = (mk(VAR, 0, self.here(s), owner=o) for s in v)
            n = [self.nfree.pop() for _ in range(4)]
            for s in n:
                self.nown[s] = o
            self.nodes[n[0]] = [x11, x12]; self.nodes[n[1]] = [x21, x22]
            self.nodes[n[2]] = [x11, x21]; self.nodes[n[3]] = [x12, x22]
            self.push(a1, with_payload(b, self.here(n[0]))); self.push(a2, with_payload(b, self.here(n[1])))
            self.push(b1, with_payload(a, self.here(n[2]))); self.push(b2, with_payload(a, self.here(n[3])))
            return 2 + 3
        if la or lb:
            if not la:
                a, b = b, a
            if not self.can_send():
                self.queue.append((T_LINK, a, b)); self.st["retry"] = self.st.get("retry", 0) + 1
                return 0
            if self.fab.gran[0]:
                self.gran(a, False)
            a1, a2 = self.free_node(a)
            self.send(MSG_NODE, addr_xy(payload(b)), a, a1, a2, b)
            return 1
        self.send_or_retry(MSG_LINK, addr_xy(payload(a)), a, b)
        return 0

    def forward(self, q, p):
        """PULL, second half: send LINK(q ~ p) to q's cell, whose NODE rule migrates q here."""
        if self.oob(q):
            return self.trap(TRAP_OOB, q)
        if self.can_send():
            self.send(MSG_LINK, addr_xy(payload(q)), q, p)
        else:
            self.queue.append((T_FWD, q, p)); self.st["retry"] = self.st.get("retry", 0) + 1
        return 0

    # ---- engine step ----
    def engine(self, rng):
        if self.vh_busy:
            self.vh_busy -= 1
            self.st["vhu"] += 1
        if self.busy:
            self.busy -= 1
            self.st["busy"] += 1
            return
        if self.vh_out is not None and not self.vh_busy:
            a, b = self.vh_out
            self.vh_out = None
            self.cur_rs = False
            self.st["tasks"] += 1
            self.busy = max(0, self.do_link(a, b))
            return
        src = None
        if self.rs is not None and self.rs_tm > 0:
            self.rs_tm -= 1
        msg_ok = bool(self.eject)
        self.update_roomy()
        if msg_ok and self.eject[0][0] in (MSG_NODE, MSG_PULL) and not self.nfree:
            msg_ok = False
        if msg_ok and self.queue:
            p = self.fab.p_msg if self.can_send() else 1.0
            src = "m" if rng.random() < p else "q"
        elif msg_ok:
            src = "m"
        elif self.queue:
            src = "q"
        if src != "m" and self.rs is not None and self.rs_tm == 0:
            src = "r"                          # the parked retry before the task stack (non-LIFO)
        if src is None:
            return
        if self.fab.p_stall and rng.random() < self.fab.p_stall:
            self.busy = 1
            return
        self.st["tasks"] += 1
        self.cur_rs = src == "r"
        if src in ("q", "r"):
            if src == "r":
                (k, a, b), self.rs = self.rs, None
                self.cur_rsn = self.rs_n
            else:
                k, a, b = self.queue.pop()   # LIFO task stack (depth-first, bounded memory)
            vh = None
            if k == T_LINK and not self.vh_busy and self.vh_out is None:
                vh = self.vhu_chain(a, b)          # hand the var chain to the VHU (no-op if not a local var link)
            if vh is not None and vh[0]:
                self.vh_busy, self.vh_out = vh[0], vh[1]
                cost = 1
            elif k == T_LINK:
                cost = 1 + self.do_link(a, b)
            elif k == T_SPAWN:
                cost = 1 + self.spawn(a, b)
            elif k == T_FWD:
                cost = 1 + self.forward(a, b)
            else:
                cost = 1 + self.expand(a, b)
        else:
            m = self.eject.popleft()
            self.st["msgs_in"] += 1
            kind = m[0]
            if kind == MSG_LINK:
                cost = 1 + self.do_link(m[3], m[4])
            elif kind == MSG_SPAWN:
                if self.cross(m[3], m[4]):
                    cost = 1 + self.trap(TRAP_CROSS, min(m[3], m[4], key=owner))
                else:
                    self.job = label(m[3]) % GT_N if self.fab.gran[0] else None
                    cost = 1 + self.expand(m[3], m[4])
                    self.job = None
            else:
                if self.cross(m[3], m[6]):
                    cost = 1 + self.trap(TRAP_CROSS, min(m[3], m[6], key=owner))
                else:
                    s = self.nfree.pop()
                    self.nodes[s] = [m[4], m[5]]; self.nown[s] = owner(m[3])
                    if kind == MSG_PULL:
                        cost = 1 + self.forward(m[6], with_payload(m[3], self.here(s)))
                    else:
                        self.node_in = True
                        cost = 1 + self.do_link(with_payload(m[3], self.here(s)), m[6])
                        self.node_in = False
        if len(self.queue) > self.fab.qdepth:
            raise FabricError(f"task queue overflow at cell {self.x},{self.y}")
        self.st["max_q"] = max(self.st["max_q"], len(self.queue))
        self.st["max_nodes"] = max(self.st["max_nodes"], len(self.nodes) - len(self.nfree))
        self.st["max_vars"] = max(self.st.get("max_vars", 0), len(self.vars) - len(self.vfree))
        self.busy = max(0, cost - 1)

    def idle(self):
        return not (self.busy or self.vh_busy or self.vh_out or self.queue or self.eject or self.rs or any(self.inq.values()))


class Fabric:
    def __init__(self, book, W, H, slots=1024, qdepth=1024, fifo_depth=4, seed=0,
                 p_jitter=0.0, p_stall=0.0, p_msg=0.5, img=None, fi_nosend=False, cluster=(2, 2, 1), spawn_k=None, spawn_hint=None, link_local=None, spawn_k2=None, gran=None):
        self.book, self.W, self.H = book, W, H
        # sender-side spawn threshold (step 11, SPEC 5): hand a REF expansion to a hungry neighbour only
        # while more than spawn_k tasks wait on the local task stack (-1 = always, the step-10 policy)
        self.spawn_k = SPAWN_K if spawn_k is None else spawn_k
        self.spawn_hint = SPAWN_HINT if spawn_hint is None else spawn_hint
        self.link_local = LINK_LOCAL if link_local is None else link_local
        self.spawn_k2 = SPAWN_K2 if spawn_k2 is None else spawn_k2
        self.gran = tuple(GRAN if gran is None else gran)
        # cluster definition ROM (SPEC 5.6): CW x CH cells share one ROM with NP read ports.  An
        # EXPAND reads max(nodes, redexes) template entries, two per ROM word (one grant per pair); a cell whose
        # cluster's ports are all busy waits (the RTL interleaves cycle by cycle with a round-robin
        # arbiter; the model reserves a port for the whole template, an approximation).
        self.cw, self.ch, self.rom_np = cluster
        self.rom_free = {}
        self.rom_wait_cycles = 0
        self.fi_nosend = fi_nosend
        self.fifo_depth, self.qdepth = fifo_depth, qdepth
        self.rng = random.Random(seed)
        self.p_jitter, self.p_stall, self.p_msg = p_jitter, p_stall, p_msg
        self.img = img or Image(book, W, H, slots, qdepth)
        self.slots = self.img.slots
        self.cells = {(x, y): Cell(self, x, y, self.img) for x in range(W) for y in range(H)}
        self.interactions = 0
        self.msgs = [0, 0, 0, 0]
        self.hops = 0
        self.cycles = 0

    def rom_wait(self, cell, n):
        if n == 0:
            return 0
        ports = self.rom_free.setdefault((cell.x // self.cw, cell.y // self.ch), [0] * self.rom_np)
        j = min(range(len(ports)), key=ports.__getitem__)
        start = max(self.cycles + 1, ports[j])
        ports[j] = start + n
        self.rom_wait_cycles += start - (self.cycles + 1)
        return start - (self.cycles + 1)

    def route(self, c, m):
        dx, dy = m[1], m[2]
        if dx > c.x: return "E"
        if dx < c.x: return "W"
        if dy > c.y: return "S"
        if dy < c.y: return "N"
        return "X"

    def router_step(self):
        moves = []
        for c in self.cells.values():
            req = {}
            for i in DIRS + ["L"]:
                q = c.inq[i]
                if q:
                    req.setdefault(self.route(c, q[0]), []).append(i)
            for o, ins in req.items():
                if self.p_jitter and self.rng.random() < self.p_jitter:
                    continue
                i = self.rng.choice(ins) if len(ins) > 1 else ins[0]
                if o == "X":
                    if len(c.eject) < self.fifo_depth:
                        moves.append((c, i, c.eject))
                else:
                    n = self.cells[c.nbr_xy(o)]
                    dst = n.inq[OPP[o]]
                    if len(dst) < self.fifo_depth:
                        moves.append((c, i, dst))
        for c, i, dst in moves:
            dst.append(c.inq[i].popleft())
            if dst is not c.eject:
                self.hops += 1

    def step(self):
        self.router_step()
        cells = list(self.cells.values())
        self.rng.shuffle(cells)
        for c in cells:
            c.engine(self.rng)
        self.cycles += 1

    def run(self, max_cycles=10**8):
        last, last_c = -1, 0
        while True:
            self.step()
            if self.interactions != last:
                last, last_c = self.interactions, self.cycles
            elif self.cycles - last_c > 100000:
                raise FabricError("no progress for 100000 cycles (out of memory / livelock)")
            if all(c.idle() for c in self.cells.values()):
                return self
            if self.cycles >= max_cycles:
                raise FabricError("cycle limit (deadlock or livelock?)")

    def readback(self, k=0):
        nodes = {k2: c.nodes for k2, c in self.cells.items()}
        vars_ = {k2: c.vars for k2, c in self.cells.items()}
        return readback_dump(self.book, nodes, vars_, self.img.roots[k])

    def traps(self):
        return sorted(set((r, o) for c in self.cells.values() for r, o, _ in c.traps))

    def tenant_results(self):
        out = []
        for k, t in enumerate(self.img.tenants):
            try:
                rb = self.readback(k)
            except Exception as e:
                rb = f"ERROR {type(e).__name__}"
            out.append({"owner": t["owner"], "readback": rb,
                        "nodes": sum(1 for c in self.cells.values() for s, e in enumerate(c.nodes)
                                     if e is not None and c.nown[s] == t["owner"])})
        return out

    def node_count(self):
        return sum(sum(e is not None for e in c.nodes) for c in self.cells.values())

    def report(self):
        busy = [c.st["busy"] + c.st["tasks"] for c in self.cells.values()]
        return {"cycles": self.cycles, "interactions": self.interactions, "rom_wait": self.rom_wait_cycles, "msgs": dict(zip(MSG_NAMES, self.msgs)),
                "hops": self.hops, "util": sum(busy) / (len(busy) * max(1, self.cycles)),
                "per_cell_interactions": {k: c.st["interactions"] for k, c in self.cells.items()}}
