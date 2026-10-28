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

MSG_LINK, MSG_NODE, MSG_SPAWN = 0, 1, 2
MSG_NAMES = ["LINK", "NODE", "SPAWN"]
T_LINK, T_EXPAND, T_SPAWN = 0, 1, 2
DIRS = ["N", "E", "S", "W"]
DXY = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0)}
OPP = {"N": "S", "S": "N", "E": "W", "W": "E"}


class FabricError(Exception):
    pass


# ---------------------------------------------------------------------------------------------
# Loader: memory image (shared with the RTL testbench)
# ---------------------------------------------------------------------------------------------
class Image:
    """Initial distribution of @main over the cells + book ROM.  Root var = cell(0,0) var slot 0."""

    def __init__(self, book, W, H, slots=1024, qdepth=1024, main_cells=None):
        self.book, self.W, self.H, self.slots, self.qdepth = book, W, H, slots, qdepth
        self.nodes = {(x, y): [None] * slots for x in range(W) for y in range(H)}
        self.vars = {(x, y): [None] * slots for x in range(W) for y in range(H)}
        self.queue = {(x, y): [] for x in range(W) for y in range(H)}
        self.vars[(0, 0)][0] = mk(NONE)
        self.root = mk(VAR, 0, addr(0, 0, 0))
        order = main_cells or [(x, y) for y in range(H) for x in range(W)]
        d = book["main"]

        def alloc(kind):
            for c in order:
                tab = self.nodes[c] if kind == "n" else self.vars[c]
                for s in range(slots):
                    if tab[s] is None:
                        tab[s] = mk(NONE) if kind == "v" else [0, 0]
                        return addr(c[0], c[1], s)
            raise FabricError("@main does not fit in the fabric")
        vmap = [alloc("v") for _ in range(d.nvars)]
        nmap = [alloc("n") for _ in range(len(d.nodes))]

        def tr(p):
            t = tag(p)
            if t == VAR: return mk(VAR, 0, vmap[payload(p)])
            if t in NODE_TAGS: return with_payload(p, nmap[payload(p)])
            return p
        for j, (_, a, b) in enumerate(d.nodes):
            x, y = addr_xy(nmap[j])
            self.nodes[(x, y)][addr_slot(nmap[j])] = [tr(a), tr(b)]
        self.queue[(0, 0)].append((T_LINK, tr(d.root), self.root))
        for a, b in d.redexes:
            self.queue[(0, 0)].append((T_LINK, tr(a), tr(b)))
        # book ROM: dir[id] = entry index of header; header = (root, counts); then nodes, then redexes
        self.rom = []
        self.dir = []
        for dd in book.defs:
            self.dir.append(len(self.rom))
            cnt = len(dd.nodes) | (dd.nvars << 8) | (len(dd.redexes) << 16)
            if len(dd.nodes) > 255 or dd.nvars > 255 or len(dd.redexes) > 255:
                raise FabricError(f"definition @{dd.name} too large for one EXPAND")
            self.rom.append((dd.root, cnt))
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
                for e in tab:
                    f.write(h(0 if e is None else (e[1] << 64) | e[0], 32) + "\n")
            with open(f"{outdir}/nalloc_{x}_{y}.hex", "w") as f:
                for e in tab:
                    f.write("0\n" if e is None else "1\n")
            with open(f"{outdir}/var_{x}_{y}.hex", "w") as f:
                for e in self.vars[(x, y)]:
                    f.write(h(0 if e is None else e, 16) + "\n")
            with open(f"{outdir}/valloc_{x}_{y}.hex", "w") as f:
                for e in self.vars[(x, y)]:
                    f.write("0\n" if e is None else "1\n")
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
        with open(f"{outdir}/dir.hex", "w") as f:
            for d in self.dir:
                f.write(h(d, 4) + "\n")
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


# ---------------------------------------------------------------------------------------------
# Cycle model
# ---------------------------------------------------------------------------------------------
class Cell:
    def __init__(self, fab, x, y, img):
        self.fab, self.x, self.y = fab, x, y
        self.nodes = [None if e is None else list(e) for e in img.nodes[(x, y)]]
        self.vars = list(img.vars[(x, y)])
        self.nfree = [s for s in range(img.slots - 1, -1, -1) if self.nodes[s] is None]
        self.vfree = [s for s in range(img.slots - 1, -1, -1) if self.vars[s] is None]
        self.queue = deque(img.queue[(x, y)])
        self.inq = {d: deque() for d in DIRS + ["L"]}     # router input FIFOs (L = local outbox)
        self.eject = deque()
        self.busy = 0
        self.rr = 0
        self.nbrs = [d for d in ("E", "S", "W", "N")
                     if 0 <= x + DXY[d][0] < fab.W and 0 <= y + DXY[d][1] < fab.H]
        self.spawn_targets = [None] + self.nbrs
        self.st = {"interactions": 0, "busy": 0, "tasks": 0, "msgs_in": 0, "requeue": 0, "max_q": len(self.queue),
                   "max_nodes": 0}

    # ---- helpers ----
    def local(self, p):
        return addr_xy(payload(p)) == (self.x, self.y)

    def can_send(self):
        return len(self.inq["L"]) < self.fab.fifo_depth

    def send(self, kind, dst, *pl):
        assert self.can_send()
        self.inq["L"].append((kind, dst[0], dst[1]) + pl)
        self.fab.msgs[kind] += 1

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
        self.nodes[s] = None
        self.nfree.append(s)
        return e

    def here(self, slot):
        return addr(self.x, self.y, slot)

    def nbr_xy(self, d):
        return self.x + DXY[d][0], self.y + DXY[d][1]

    def count(self):
        self.st["interactions"] += 1
        self.fab.interactions += 1

    # ---- link (SPEC 4) ----
    def do_link(self, a, b):
        cost = 0
        while True:
            cost += 1
            if not is_var(a):
                if not is_var(b):
                    return cost + self.redex(a, b)
                a, b = b, a
            if not self.local(a):
                self.send_or_retry(MSG_LINK, addr_xy(payload(a)), a, b)
                return cost
            s = addr_slot(payload(a))
            old = self.vars[s]
            if old is None:
                raise FabricError(f"link into free var {show_port(a)} at {self.x},{self.y}")
            if tag(old) == NONE:
                self.vars[s] = b
                return cost
            self.vars[s] = None
            self.vfree.append(s)
            a = old

    def spawn(self, ref, x):
        t = self.spawn_targets[self.rr % len(self.spawn_targets)]
        self.rr += 1
        if t is None:
            return self.expand(ref, x)
        self.send_or_retry(MSG_SPAWN, self.nbr_xy(t), mk(REF, ref), x)
        return 1

    def expand(self, ref, x, forwarded=False):
        d = self.fab.book[ref]
        nn, nv = len(d.nodes), d.nvars
        if len(self.nfree) < nn or len(self.vfree) < nv:
            if self.nbrs:
                t = self.nbrs[self.rr % len(self.nbrs)]
                self.rr += 1
                self.send_or_retry(MSG_SPAWN, self.nbr_xy(t), mk(REF, ref), x)
                self.st["requeue"] += 1
                return 1
            raise FabricError("out of memory (1x1 fabric cannot place expansion)")
        nmap = [self.nfree[-1 - j] for j in range(nn)]
        vmap = [self.vfree[-1 - i] for i in range(nv)]
        del self.nfree[len(self.nfree) - nn:]
        del self.vfree[len(self.vfree) - nv:]
        for s in vmap:
            self.vars[s] = mk(NONE)

        def tr(p):
            t = tag(p)
            if t == VAR: return mk(VAR, 0, self.here(vmap[payload(p)]))
            if t in NODE_TAGS: return with_payload(p, self.here(nmap[payload(p)]))
            return p
        for j, (_, a, b) in enumerate(d.nodes):
            self.nodes[nmap[j]] = [tr(a), tr(b)]
        self.push(tr(d.root), x)
        for a, b in d.redexes:
            self.push(tr(a), tr(b))
        return 1 + nn + 1 + len(d.redexes)

    # ---- redex (SPEC 3, 6) ----
    def redex(self, a, b):
        ta, tb = tag(a), tag(b)
        if ta < tb or (ta == tb and label(a) < label(b)):
            a, b, ta, tb = b, a, tb, ta
        if ta <= NUM:
            self.count()
            if tb == REF and ta != ERA:
                return self.spawn(label(b), a)
            return 0
        if tb <= NUM:
            if tb == REF and ta != DUP:
                self.count()
                return self.spawn(label(b), a)
            if not self.local(a):
                self.send_or_retry(MSG_LINK, addr_xy(payload(a)), a, b)
                return 0
            if ta == SWI and tb == NUM and payload(b) != 0 and not self.nfree:
                self.queue.append((T_LINK, a, b)); self.st["requeue"] += 1
                return 0
            self.count()
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
                    self.nodes[m] = [b, a2]
                    self.push(a1, mk(OPR, op | ((1 - s) << 4), self.here(m)))
                return 1 + 1
            # SWI
            if x == 0:
                c = self.nfree.pop()
                self.nodes[c] = [a2, ERA_P]
                self.push(a1, mk(CON, 0, self.here(c)))
            else:
                c1 = self.nfree.pop()
                c2 = self.nfree.pop()
                self.nodes[c1] = [num(x - 1), a2]
                self.nodes[c2] = [ERA_P, mk(CON, 0, self.here(c1))]
                self.push(a1, mk(CON, 0, self.here(c2)))
            return 1 + 1
        la, lb = self.local(a), self.local(b)
        if la and lb:
            anni = ta == tb and label(a) == label(b) and ta in (CON, DUP)
            if not anni and (len(self.nfree) < 2 or len(self.vfree) < 4):
                self.queue.append((T_LINK, a, b)); self.st["requeue"] += 1
                return 0
            self.count()
            a1, a2 = self.free_node(a)
            b1, b2 = self.free_node(b)
            if anni:
                self.push(a1, b1); self.push(a2, b2)
                return 1 + 2
            v = [self.vfree.pop() for _ in range(4)]
            for s in v:
                self.vars[s] = mk(NONE)
            x11, x12, x21, x22 = (mk(VAR, 0, self.here(s)) for s in v)
            n = [self.nfree.pop() for _ in range(4)]
            self.nodes[n[0]] = [x11, x12]; self.nodes[n[1]] = [x21, x22]
            self.nodes[n[2]] = [x11, x21]; self.nodes[n[3]] = [x12, x22]
            self.push(a1, with_payload(b, self.here(n[0]))); self.push(a2, with_payload(b, self.here(n[1])))
            self.push(b1, with_payload(a, self.here(n[2]))); self.push(b2, with_payload(a, self.here(n[3])))
            return 2 + 4
        if la or lb:
            if not la:
                a, b = b, a
            if not self.can_send():
                self.queue.append((T_LINK, a, b)); self.st["retry"] = self.st.get("retry", 0) + 1
                return 0
            a1, a2 = self.free_node(a)
            self.send(MSG_NODE, addr_xy(payload(b)), a, a1, a2, b)
            return 1
        self.send_or_retry(MSG_LINK, addr_xy(payload(a)), a, b)
        return 0

    # ---- engine step ----
    def engine(self, rng):
        if self.busy:
            self.busy -= 1
            self.st["busy"] += 1
            return
        src = None
        msg_ok = bool(self.eject)
        if msg_ok and self.eject[0][0] == MSG_NODE and not self.nfree:
            msg_ok = False
        if msg_ok and self.queue:
            p = self.fab.p_msg if self.can_send() else 1.0
            src = "m" if rng.random() < p else "q"
        elif msg_ok:
            src = "m"
        elif self.queue:
            src = "q"
        else:
            return
        if self.fab.p_stall and rng.random() < self.fab.p_stall:
            self.busy = 1
            return
        self.st["tasks"] += 1
        if src == "q":
            k, a, b = self.queue.pop()   # LIFO task stack (depth-first, bounded memory)
            if k == T_LINK:
                cost = 1 + self.do_link(a, b)
            elif k == T_SPAWN:
                cost = 1 + self.spawn(label(a), b)
            else:
                cost = 1 + self.expand(label(a), b)
        else:
            m = self.eject.popleft()
            self.st["msgs_in"] += 1
            kind = m[0]
            if kind == MSG_LINK:
                cost = 1 + self.do_link(m[3], m[4])
            elif kind == MSG_SPAWN:
                cost = 1 + self.expand(label(m[3]), m[4])
            else:
                s = self.nfree.pop()
                self.nodes[s] = [m[4], m[5]]
                cost = 1 + self.do_link(with_payload(m[3], self.here(s)), m[6])
        if len(self.queue) > self.fab.qdepth:
            raise FabricError(f"task queue overflow at cell {self.x},{self.y}")
        self.st["max_q"] = max(self.st["max_q"], len(self.queue))
        self.st["max_nodes"] = max(self.st["max_nodes"], len(self.nodes) - len(self.nfree))
        self.st["max_vars"] = max(self.st.get("max_vars", 0), len(self.vars) - len(self.vfree))
        self.busy = max(0, cost - 1)

    def idle(self):
        return not (self.busy or self.queue or self.eject or any(self.inq.values()))


class Fabric:
    def __init__(self, book, W, H, slots=1024, qdepth=1024, fifo_depth=4, seed=0,
                 p_jitter=0.0, p_stall=0.0, p_msg=0.5, img=None):
        self.book, self.W, self.H = book, W, H
        self.fifo_depth, self.qdepth = fifo_depth, qdepth
        self.rng = random.Random(seed)
        self.p_jitter, self.p_stall, self.p_msg = p_jitter, p_stall, p_msg
        self.img = img or Image(book, W, H, slots, qdepth)
        self.cells = {(x, y): Cell(self, x, y, self.img) for x in range(W) for y in range(H)}
        self.interactions = 0
        self.msgs = [0, 0, 0]
        self.hops = 0
        self.cycles = 0

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

    def readback(self):
        nodes = {k: c.nodes for k, c in self.cells.items()}
        vars_ = {k: c.vars for k, c in self.cells.items()}
        return readback_dump(self.book, nodes, vars_)

    def node_count(self):
        return sum(sum(e is not None for e in c.nodes) for c in self.cells.values())

    def report(self):
        busy = [c.st["busy"] + c.st["tasks"] for c in self.cells.values()]
        return {"cycles": self.cycles, "interactions": self.interactions, "msgs": dict(zip(MSG_NAMES, self.msgs)),
                "hops": self.hops, "util": sum(busy) / (len(busy) * max(1, self.cycles)),
                "per_cell_interactions": {k: c.st["interactions"] for k, c in self.cells.items()}}
