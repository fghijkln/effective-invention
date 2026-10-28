"""Pure semantic reducer (golden model).  Any redex order; links are atomic.

Implements exactly the rule table of SPEC.md section 3.  Addresses here are plain integers
(no cells).  Interaction count, node count and the canonical readback of the root are
schedule-independent (strong confluence) and are what the fabric/RTL results are checked against.
"""
import random
from .ports import *
from . import ir


class OutOfFuel(Exception):
    pass


class Net:
    def __init__(self, book, geometry=None):
        self.book = book
        self.geometry = geometry   # (W, H, SLOTS) of the fabric being predicted: classifies forged pointers
        self.nodes = {}      # addr -> [aux1, aux2]
        self.vars = {}       # addr -> port (NONE = unsubstituted)
        self.nown = {}       # addr -> owner tag of the node slot
        self.vown = {}       # addr -> owner tag of the var slot
        self.absmap = {}     # fabric address of a tenant root var -> semantic var id
        self.traps = []      # (reason, owner of the offending port, target address)
        self.next_node = 1
        self.next_var = 1
        self.rdx = []
        self.stats = {"interactions": 0, "anni": 0, "comm": 0, "eras": 0, "oper": 0, "swit": 0, "expand": 0, "copy": 0, "void": 0, "links": 0}

    # --- allocation -------------------------------------------------------
    def alloc_node(self, a1, a2, o=0):
        n = self.next_node; self.next_node += 1
        self.nodes[n] = [a1, a2]
        self.nown[n] = o
        return n

    def alloc_var(self, o=0):
        v = self.next_var; self.next_var += 1
        self.vars[v] = mk(NONE)
        self.vown[v] = o
        return v

    # --- owner-capability checks (SPEC 12) ---------------------------------
    def trap(self, reason, p):
        self.traps.append((reason, owner(p), payload(p)))
        self.stats["traps"] = self.stats.get("traps", 0) + 1

    def oob(self, p):
        """A forged (absolute) pointer outside the fabric geometry."""
        if not (p & ABS_BIT) or self.geometry is None:
            return False
        W, H, S = self.geometry
        a = payload(p); x, y = addr_xy(a)
        return x >= W or y >= H or addr_slot(a) >= S or (a & 0xFF00F000) != 0

    def cross(self, a, b):
        return is_cap(a) and is_cap(b) and owner(a) != owner(b)

    # --- linking ----------------------------------------------------------
    def link(self, a, b):
        while True:
            self.stats["links"] += 1
            if self.cross(a, b):
                self.trap(TRAP_CROSS, a if owner(a) < owner(b) else b); return
            if not is_var(a):
                if not is_var(b):
                    self.rdx.append((a, b)); return
                a, b = b, a
            if self.oob(a):
                self.trap(TRAP_OOB, a); return
            v = payload(a)
            if a & ABS_BIT or self.vown.get(v) != owner(a):
                self.trap(TRAP_FORGED, a); return
            old = self.vars[v]
            if tag(old) == NONE:
                self.vars[v] = b; return
            del self.vars[v]
            del self.vown[v]
            a = old

    # --- definitions ------------------------------------------------------
    def instantiate(self, did, x=None, o=0, patch=None):
        """Expand definition `did` for owner `o` (every capability port is stamped with o)."""
        d = self.book[did]
        vmap = [self.alloc_var(o) for _ in range(d.nvars)]
        nmap = [self.next_node + i for i in range(len(d.nodes))]
        self.next_node += len(d.nodes)

        def tr(p):
            t = tag(p)
            if p & ABS_BIT:
                if t == VAR and payload(p) in self.absmap:
                    return mk(VAR, 0, self.absmap[payload(p)], owner=o)
                return with_owner(p, o)      # forged pointer: keeps its ABS mark, traps when used
            if t == VAR: return mk(VAR, 0, vmap[payload(p)], owner=o)
            if t in NODE_TAGS: return with_owner(with_payload(p, nmap[payload(p)]), o)
            return stamp(p, o)
        for j, (_, a, b) in enumerate(d.nodes):
            self.nodes[nmap[j]] = [tr(a), tr(b)]
            self.nown[nmap[j]] = o
        root = tr(d.root)
        links = ([(root, x)] if x is not None else []) + [(tr(a), tr(b)) for a, b in d.redexes]
        if patch:
            links = patch(links)
        for a, b in links:
            self.link(a, b)
        return root

    def deref(self, p):
        """Consume the node p points at; returns its aux ports, or None after a trap."""
        if self.oob(p):
            self.trap(TRAP_OOB, p); return None
        n = payload(p)
        if p & ABS_BIT or self.nown.get(n) != owner(p):
            self.trap(TRAP_FORGED, p); return None
        del self.nown[n]
        return self.nodes.pop(n)

    # --- interaction ------------------------------------------------------
    def interact(self, a, b):
        ta, tb = tag(a), tag(b)
        if ta < tb or (ta == tb and label(a) < label(b)):
            a, b, ta, tb = b, a, tb, ta
        st = self.stats
        o = owner(a) if is_cap(a) else owner(b)
        # forged / out-of-bounds node pointers trap before anything is consumed or counted.  Only
        # nodes the rule actually reads are checked (REF ~ CON/OPR/SWI expands without reading).
        if tb <= NUM and ta > NUM and tb == REF and ta != DUP:
            chk = ()
        else:
            chk = tuple(p for p in (a, b) if is_node(p))
        for p in chk:
            if self.oob(p):
                self.trap(TRAP_OOB, p); return
        for p in chk:
            if (p & ABS_BIT) or self.nown.get(payload(p)) != owner(p):
                self.trap(TRAP_FORGED, p); return
        st["interactions"] += 1
        # both nullary: REF=2 ERA=3 NUM=4
        if ta <= NUM:
            if tb == REF and ta != ERA:
                # REF ~ NUM / REF ~ REF: expand b (the smaller label for REF~REF)
                st["expand"] += 1
                self.instantiate(label(b), a, owner(b))
            else:
                st["void"] += 1
            return
        if tb <= NUM:
            if tb == REF:
                if ta == DUP:
                    st["copy"] += 1
                    a1, a2 = self.deref(a)
                    self.link(a1, b); self.link(a2, b)
                else:
                    st["expand"] += 1
                    self.instantiate(label(b), a, owner(b))
                return
            a1, a2 = self.deref(a)
            if tb == ERA:
                st["eras"] += 1
                self.link(a1, ERA_P); self.link(a2, ERA_P); return
            # tb == NUM
            if ta in (CON, DUP):
                st["copy"] += 1
                self.link(a1, b); self.link(a2, b); return
            x = payload(b)
            if ta == OPR:
                st["oper"] += 1
                l = label(a); op, s = l & 15, l >> 4
                if tag(a1) == NUM:
                    y = payload(a1)
                    self.link(a2, num(apply_op(op, y, x) if s else apply_op(op, x, y)))
                else:
                    m = self.alloc_node(b, a2, o)
                    self.link(a1, mk(OPR, op | ((1 - s) << 4), m, owner=o))
                return
            # SWI
            st["swit"] += 1
            if x == 0:
                c = self.alloc_node(a2, ERA_P, o)
                self.link(a1, mk(CON, 0, c, owner=o))
            else:
                c1 = self.alloc_node(num(x - 1), a2, o)
                c2 = self.alloc_node(ERA_P, mk(CON, 0, c1, owner=o), o)
                self.link(a1, mk(CON, 0, c2, owner=o))
            return
        # both binary
        a1, a2 = self.deref(a)
        b1, b2 = self.deref(b)
        if ta == tb and label(a) == label(b) and ta in (CON, DUP):
            st["anni"] += 1
            self.link(a1, b1); self.link(a2, b2); return
        st["comm"] += 1
        x11, x12, x21, x22 = (mk(VAR, 0, self.alloc_var(o), owner=o) for _ in range(4))
        nb1 = self.alloc_node(x11, x12, o); nb2 = self.alloc_node(x21, x22, o)
        na1 = self.alloc_node(x11, x21, o); na2 = self.alloc_node(x12, x22, o)
        self.link(a1, with_payload(b, nb1)); self.link(a2, with_payload(b, nb2))
        self.link(b1, with_payload(a, na1)); self.link(b2, with_payload(a, na2))

    def normalize(self, seed=None, fuel=10**7, order="random"):
        rng = random.Random(seed)
        while self.rdx:
            if self.stats["interactions"] >= fuel:
                raise OutOfFuel()
            if order == "random":
                i = rng.randrange(len(self.rdx))
                self.rdx[i], self.rdx[-1] = self.rdx[-1], self.rdx[i]
                a, b = self.rdx.pop()
            elif order == "lifo":
                a, b = self.rdx.pop()
            else:
                a, b = self.rdx.pop(0)
            self.interact(a, b)


def run(book, seed=None, fuel=10**7, order="random"):
    """Reduce @main to normal form.  Returns (net, root_var)."""
    net = Net(book)
    root = net.alloc_var()
    net.instantiate(book.id("main"), mk(VAR, 0, root))
    net.normalize(seed, fuel, order)
    return net, root


# --- readback ---------------------------------------------------------------
def readback(get_node, get_var, root_port, book=None, limit=100000):
    """Canonical text of the net reachable from root_port.  get_node(port)->(aux1,aux2),
    get_var(port)->subst port.  Variables are renamed by first appearance."""
    names = {}
    seen = set()
    out = []
    budget = [limit]

    def resolve(p):
        hops = 0
        while is_var(p):
            s = get_var(p)
            if tag(s) == NONE:
                return p
            p = s
            hops += 1
            if hops > limit:
                return mk(NONE)
        return p

    def go(p):
        budget[0] -= 1
        if budget[0] < 0:
            out.append("…"); return
        p = resolve(p)
        t = tag(p)
        if t == VAR:
            k = payload(p)
            if k not in names:
                names[k] = f"x{len(names)}"
            out.append(names[k]); return
        if t == NUM: out.append(f"#{payload(p)}"); return
        if t == ERA: out.append("*"); return
        if t == REF: out.append(f"@{book.defs[label(p)].name}" if book else f"@{label(p)}"); return
        if t == NONE: out.append("?"); return
        key = (t, payload(p))
        if key in seen:
            out.append("^loop"); return
        seen.add(key)
        a, b = get_node(p)
        if t == CON: o, c = "(", ")"
        elif t == DUP: o, c = "{%d " % label(p), "}"
        elif t == OPR: o, c = "$(%s%s " % (OPS[label(p) & 15], "'" if label(p) >> 4 else ""), ")"
        else: o, c = "?(", ")"
        out.append(o); go(a); out.append(" "); go(b); out.append(c)
    go(root_port)
    return "".join(out)


def readback_net(net, root):
    try:
        return _readback_net(net, root)
    except Exception as e:      # a trapped tenant's graph may hold forged pointers
        return f"ERROR {type(e).__name__}"


def _readback_net(net, root):
    return readback(lambda p: net.nodes[payload(p)], lambda p: net.vars.get(payload(p), mk(NONE)),
                    mk(VAR, 0, root), net.book)


def run_multi(book, tenants, seed=None, fuel=10**7, order="random", geometry=None):
    """Several mutually distrusting programs in one net.  tenants: list of dicts
    {"owner": o (0..14), "main": definition id, "patch": optional fn(links)->links (fault injection on
    the initial links)}.  Tenant k's root var is the var the fabric puts at cell (0,0) slot k."""
    net = Net(book, geometry)
    roots = []
    for k, t in enumerate(tenants):
        assert 0 <= t["owner"] < OWNER_FREE
        r = net.alloc_var(t["owner"])
        net.absmap[addr(0, 0, k)] = r
        roots.append(r)
    for k, t in enumerate(tenants):
        net.instantiate(t["main"], mk(VAR, 0, roots[k], owner=t["owner"]), t["owner"], t.get("patch"))
    net.normalize(seed, fuel, order)
    return net, roots


def result_multi(book, tenants, seed=None, fuel=10**7, order="random", geometry=None):
    net, roots = run_multi(book, tenants, seed, fuel, order, geometry)
    per = []
    for k, t in enumerate(tenants):
        o = t["owner"]
        per.append({"owner": o, "readback": readback_net(net, roots[k]),
                    "nodes": sum(1 for n in net.nown.values() if n == o)})
    return {"tenants": per, "interactions": net.stats["interactions"], "nodes": len(net.nodes),
            "traps": sorted(set((r, o) for r, o, _ in net.traps)), "trap_list": list(net.traps)}


def result(book, seed=None, fuel=10**7, order="random"):
    net, root = run(book, seed, fuel, order)
    return {"readback": readback_net(net, root), "interactions": net.stats["interactions"],
            "nodes": len(net.nodes), "stats": dict(net.stats)}
