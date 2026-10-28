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
        for dd in book.defs:
            self.dir.append(len(self.rom))
            cnt = len(dd.nodes) | (dd.nvars << 8) | (len(dd.redexes) << 16)
            if len(dd.nodes) > XMAP or dd.nvars > XMAP or len(dd.redexes) > 255:
                raise FabricError(f"definition @{dd.name} too large for one EXPAND "
                                  f"({len(dd.nodes)} nodes / {dd.nvars} vars, limit {XMAP})")
            self.rom.append((dd.root, cnt))
            self.dir3.append(len(self.romn) | (len(self.romr) << 16) | (cnt << 32) | (dd.root << 64))
            self.romn += [(a, b) for (_, a, b) in dd.nodes]
            self.romr += list(dd.redexes)
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
        with open(f"{outdir}/romn.hex", "w") as f:
            for a, b in self.romn:
                f.write(h((b << 64) | a, 32) + "\n")
        with open(f"{outdir}/romr.hex", "w") as f:
            for a, b in self.romr or [(0, 0)]:
                f.write(h((b << 64) | a, 32) + "\n")
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

    # ---- link (SPEC 4) ----
    def do_link(self, a, b):
        cost = 0
        while True:
            cost += 1
            if not is_var(a) and is_var(b):
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

    def remote_target(self, a, b):
        """Would this link/redex leave the cell (used only by the fault-injection knob)?"""
        if is_var(a):
            return self.oob(a) or not self.local(a)
        return any(is_node(p) and (self.oob(p) or not self.local(p)) for p in (a, b))

    def hungry(self):
        return not (self.busy or self.queue or self.eject)

    def spawn(self, ref, x):
        """Demand-driven work distribution: hand the expansion to a hungry neighbour (one that
        advertises an empty task stack on its side-band wire), otherwise expand locally."""
        self.hrot = (getattr(self, "hrot", self.x + self.y)) + 1
        order = ["N", "E", "S", "W"]
        for k in range(4):
            d = order[(self.hrot - 1 + k) % 4]
            if d in self.nbrs and self.fab.cells[self.nbr_xy(d)].hungry() and self.can_send():
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
        self.push(tr(d.root), x)
        for a, b in d.redexes:
            self.push(tr(a), tr(b))
        return 1 + max(nn, nv) + 1 + len(d.redexes)

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
                self.queue.append((T_LINK, a, b)); self.st["requeue"] += 1
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
                self.queue.append((T_LINK, a, b)); self.st["requeue"] += 1
                return 0
            self.count()
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
                cost = 1 + self.spawn(a, b)
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
                    cost = 1 + self.expand(m[3], m[4])
            else:
                if self.cross(m[3], m[6]):
                    cost = 1 + self.trap(TRAP_CROSS, min(m[3], m[6], key=owner))
                else:
                    s = self.nfree.pop()
                    self.nodes[s] = [m[4], m[5]]; self.nown[s] = owner(m[3])
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
                 p_jitter=0.0, p_stall=0.0, p_msg=0.5, img=None, fi_nosend=False):
        self.book, self.W, self.H = book, W, H
        self.fi_nosend = fi_nosend
        self.fifo_depth, self.qdepth = fifo_depth, qdepth
        self.rng = random.Random(seed)
        self.p_jitter, self.p_stall, self.p_msg = p_jitter, p_stall, p_msg
        self.img = img or Image(book, W, H, slots, qdepth)
        self.slots = self.img.slots
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
        return {"cycles": self.cycles, "interactions": self.interactions, "msgs": dict(zip(MSG_NAMES, self.msgs)),
                "hops": self.hops, "util": sum(busy) / (len(busy) * max(1, self.cycles)),
                "per_cell_interactions": {k: c.st["interactions"] for k, c in self.cells.items()}}
