"""Step 15 probe (fabric model): where do treesum(9) 8x8's extra messages come from under step 14?
usage: probe15.py prog:n WxH seeds s14[,..] [extra Fabric kwargs as k=v ...]
Prints per-config mean cycles, msgs/int, per-kind message counts, gives by (definition, argument tag)."""
import sys, os, statistics as S
from collections import Counter
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from omega import progs, fabric
from omega.ports import tag, label
TAGN = {}
for k in dir(fabric):
    if k in ("ERA", "REF", "NUM", "CON", "DUP", "OPR", "SWI", "VAR", "NONE"):
        TAGN[getattr(fabric, k)] = k

name, n = sys.argv[1].split(":"); n = int(n)
W, H = (int(t) for t in sys.argv[2].split("x"))
seeds = range(1, int(sys.argv[3]) + 1)
modes = [int(m) for m in sys.argv[4].split(",")]
kw = {}
EXCL = set()
for a in sys.argv[5:]:
    k, v = a.split("=")
    if k == "excl":
        EXCL = {int(t) for t in v.split("/")}
    else:
        kw[k] = int(v)
b = progs.book(name, n)
names = {i: d for i, d in enumerate(getattr(b, "names", []))} if hasattr(b, "names") else {}

gives = Counter()
orig_send = fabric.Cell.send
def send(self, kind, *a, **k):
    if kind == fabric.MSG_SPAWN and getattr(self, "_ingive", False):
        gives[(label(a[1]), TAGN.get(tag(a[2]), tag(a[2])))] += 1
    return orig_send(self, kind, *a, **k)
fabric.Cell.send = send
orig_bf = fabric.Cell.bottom_fork
def bf(self):
    r = orig_bf(self)
    self._ingive = r is not None
    return r
fabric.Cell.bottom_fork = bf
orig_engine = fabric.Cell.engine
def engine(self, rng):
    self._ingive = False
    orig_engine(self, rng)
    self._ingive = False
fabric.Cell.engine = engine

for m in modes:
    cyc, mpi, kinds = [], [], Counter(); gives.clear()
    for s in seeds:
        f = fabric.Fabric(b, W, H, seed=s, s14=m, **kw)
        f.img.dqf = f.img.dqf - EXCL
        f.run()
        assert f.readback() == progs.expected(name, n), f.readback()
        r = f.report(); cyc.append(r["cycles"]); mpi.append(sum(r["msgs"].values()) / r["interactions"])
        for k, v in r["msgs"].items(): kinds[k] += v / len(seeds)
    print(f"s14={m} {kw} excl={EXCL}: cycles {S.mean(cyc):,.0f} (sd {S.stdev(cyc):,.0f})  msgs/int {S.mean(mpi):.3f}  "
          f"kinds {dict((k, round(v)) for k, v in kinds.items())}  gives/run {dict((k, round(v / len(seeds), 1)) for k, v in gives.items())}", flush=True)
