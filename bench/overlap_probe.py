"""Step 13 probe: for every SPAWN given, interactions done by the sender and by the receiver in the
next T cycles (overlap = real parallelism created by the give)."""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from omega import progs, fabric
from omega.ports import label
from collections import defaultdict
T = 64
def probe(name, n, W, H, k, k2, seed=1, gran=(0, 4, 0, 1)):
    b = progs.book(name, n)
    f = fabric.Fabric(b, W, H, seed=seed, p_msg=1.0, spawn_k=k, spawn_k2=k2, spawn_hint=1, gran=gran, qdepth=4096)
    gives = []
    osend = fabric.Cell.send
    def send(self, kind, dst, *pl):
        if kind == fabric.MSG_SPAWN:
            gives.append((f.cycles, (self.x, self.y), dst, label(pl[0])))
        return osend(self, kind, dst, *pl)
    fabric.Cell.send = send
    hist = defaultdict(dict)
    ostep = f.step
    def step():
        ostep()
        for xy, c in f.cells.items(): hist[xy][f.cycles] = c.st["interactions"]
    f.step = step
    f.run()
    fabric.Cell.send = osend
    def win(xy, t):
        h = hist[xy]; e = min(t + T, f.cycles)
        return h.get(e, 0) - h.get(t, 0)
    st = defaultdict(lambda: [0, 0, 0, 0])
    for t, s, d, r in gives:
        a, bb = win(s, t), win(d, t)
        x = st[b.defs[r].name]; x[0] += 1; x[1] += a; x[2] += bb; x[3] += min(a, bb)
    rep = f.report()
    return {"prog": f"{name}({n})", "cycles": rep["cycles"], "mpi": round(sum(rep["msgs"].values()) / rep["interactions"], 3),
            "defs": {k_: dict(n=v[0], snd=round(v[1] / v[0], 1), rcv=round(v[2] / v[0], 1), ovl=round(v[3] / v[0], 1)) for k_, v in st.items()}}
if __name__ == "__main__":
    for spec in sys.argv[1].split(","):
        nm, nn = spec.split(":")
        d = probe(nm, int(nn), 8, 8, int(sys.argv[2]), int(sys.argv[3]))
        print(d["prog"], d["cycles"], d["mpi"])
        for k_, v in sorted(d["defs"].items(), key=lambda x: -x[1]["n"]): print("   ", k_, v)
