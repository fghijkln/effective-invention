"""Step 13 probe: per-definition statistics of SPAWNed work on the fabric model.
For each received SPAWN: definition, receiver run length (interactions until the receiver is hungry
again), and the sender's activity in the 64 cycles after giving."""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from omega import progs, fabric
from omega.ports import label
from collections import defaultdict

def probe(name, n, W, H, k, k2, seed=1):
    b = progs.book(name, n)
    f = fabric.Fabric(b, W, H, seed=seed, p_msg=1.0, spawn_k=k, spawn_k2=k2, spawn_hint=1)
    stats = defaultdict(lambda: {"n": 0, "run": 0, "sbusy": 0, "sq": 0, "nout": 0, "lout": 0, "res": 0})
    jobs = {}
    pend = []   # (cycle, sender, def)
    oexp, oeng, osend = fabric.Cell.expand, fabric.Cell.engine, fabric.Cell.send
    def send(self, kind, dst, *pl):
        j = jobs.get(self)
        if j and kind in (fabric.MSG_NODE, fabric.MSG_PULL): j[2][0] += 1
        if j and kind == fabric.MSG_LINK: j[2][1] += 1
        if kind == fabric.MSG_SPAWN:
            pend.append((f.cycles, self, label(pl[0])))
        return osend(self, kind, dst, *pl)
    def engine(self, rng):
        j = jobs.get(self)
        if j and self.hungry():
            s = stats[j[0]]; s["n"] += 1; s["run"] += self.st["interactions"] - j[1]; s["nout"] += j[2][0]; s["lout"] += j[2][1]; s["res"] += j[3] - len(self.nfree); s["res"] += j[3] - len(self.nfree)
            jobs.pop(self)
        return oeng(self, rng)
    def expand(self, refp, x, forwarded=False):
        if getattr(self, "_from_msg", False):
            jobs.setdefault(self, (label(refp), self.st["interactions"], [0, 0], len(self.nfree)))
        return oexp(self, refp, x, forwarded)
    fabric.Cell.send, fabric.Cell.engine, fabric.Cell.expand = send, engine, expand
    # mark expansions coming from SPAWN messages
    oeng2 = fabric.Cell.engine
    def engine2(self, rng):
        self._from_msg = bool(self.eject) and self.eject[0][0] == fabric.MSG_SPAWN
        return oeng2(self, rng)
    fabric.Cell.engine = engine2
    # sender activity probe
    ostep = f.step
    act = defaultdict(int)
    def step():
        ostep()
        for c in f.cells.values():
            if c.busy or c.queue: act[(c, f.cycles)] = 1
    f.step = step
    f.run()
    for cyc, c, r in pend:
        stats[r]["sbusy"] += sum(act.get((c, cyc + d), 0) for d in range(1, 65))
        stats[r]["sq"] += 1
    fabric.Cell.send, fabric.Cell.engine, fabric.Cell.expand = osend, oeng, oexp
    rep = f.report()
    out = {"prog": f"{name}({n})", "mesh": f"{W}x{H}", "K": k, "K2": k2, "cycles": rep["cycles"],
           "mpi": round(sum(rep["msgs"].values()) / rep["interactions"], 3)}
    out["defs"] = {b.defs[r].name: dict(spawns=s["sq"], run=round(s["run"] / max(1, s["n"]), 1),
                   sender_busy64=round(s["sbusy"] / max(1, s["sq"]), 1), nout=round(s["nout"] / max(1, s["n"]), 2), lout=round(s["lout"] / max(1, s["n"]), 2), res=round(s["res"] / max(1, s["n"]), 2)) for r, s in stats.items()}
    return out

if __name__ == "__main__":
    for spec in sys.argv[1].split(","):
        nm, nn = spec.split(":")
        for mesh in sys.argv[2].split(","):
            W, H = map(int, mesh.split("x"))
            for kk in sys.argv[3].split(";"):
                k, k2 = map(int, kk.split(","))
                print(json.dumps(probe(nm, int(nn), W, H, k, k2)), flush=True)
