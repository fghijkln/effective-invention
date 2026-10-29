"""Where the LINK messages come from (fabric model), and how long forwarding chains get: the upper
bound on what remote-pointer path compression could save.  A LINK is a *forward* when a cell sends it
while processing a LINK message it received (the var it named was already substituted by a var in a
third cell); depth = how many forwards in a row.
usage: link_forwards.py prog:n:W [...]   (env OMEGA_SPAWN_K / OMEGA_SPAWN_HINT / OMEGA_LINK_LOCAL)"""
import sys, os, json
from collections import Counter
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from omega import progs, fabric

src = open(fabric.__file__).read()
rep = [("""            if not self.local(a):
                self.send_or_retry(MSG_LINK, addr_xy(payload(a)), a, b)
                return cost""", """            if not self.local(a):
                LS[(getattr(self, 'ctx', '?'), 'var chain' if cost > 1 else 'var', 'to var' if is_var(b) else 'to node/atom')] += 1
                self.send_or_retry(MSG_LINK, addr_xy(payload(a)), a, b)
                return cost"""),
       ("""            if not self.local(a):
                self.send_or_retry(MSG_LINK, addr_xy(payload(a)), a, b)
                return 0""", """            if not self.local(a):
                LS[(getattr(self, 'ctx', '?'), 'atom ~ remote node')] += 1
                self.send_or_retry(MSG_LINK, addr_xy(payload(a)), a, b)
                return 0"""),
       ("""        self.send_or_retry(MSG_LINK, addr_xy(payload(a)), a, b)
        return 0

    def forward""", """        LS[(getattr(self, 'ctx', '?'), 'node ~ node, both remote')] += 1
        self.send_or_retry(MSG_LINK, addr_xy(payload(a)), a, b)
        return 0

    def forward"""),
       ("""            m = self.eject.popleft()""", """            m = self.eject.popleft()
            self.ctx = 'msg' if m[0] == MSG_LINK else 'other msg'
            self.fdepth = FD.pop(id(m), 0) if m[0] == MSG_LINK else 0"""),
       ("""            if src == "r":
                (k, a, b), self.rs = self.rs, None""", """            self.ctx = 'task'
            if src == "r":
                (k, a, b), self.rs = self.rs, None"""),
       ("""        self.inq["L"].append((kind, dst[0], dst[1]) + pl)""", """        m_ = (kind, dst[0], dst[1]) + pl
        if kind == MSG_LINK and getattr(self, 'ctx', '') == 'msg':
            FD[id(m_)] = getattr(self, 'fdepth', 0) + 1
            DEP[FD[id(m_)]] += 1
        self.inq["L"].append(m_)""")]
for a, b in rep:
    assert a in src, a[:60]
    src = src.replace(a, b)
LS, FD, DEP = Counter(), {}, Counter()
g = {"LS": LS, "FD": FD, "DEP": DEP, "__name__": "omega.fabric_instr", "__package__": "omega"}
exec(compile(src, "omega/fabric_instr.py", "exec"), g)
for arg in sys.argv[1:]:
    name, n, W = arg.split(":"); n, W = int(n), int(W)
    LS.clear(); DEP.clear(); FD.clear()
    f = g["Fabric"](progs.book(name, n), W, W, seed=1, p_msg=1.0).run()
    m = f.report()["msgs"]
    fw = sum(DEP.values()); deep = sum(v for d, v in DEP.items() if d >= 2)
    print(json.dumps(dict(prog=f"{name}({n})", mesh=f"{W}x{W}", msgs=m, forwards=fw, forwards_depth2plus=deep,
                          link_sources={" / ".join(k): v for k, v in LS.most_common()})))
