"""Step 23 probe (fabric model): does the RTL's child order in rule pushes (continue with the FIRST new link,
push the rest) explain the remaining RTL/fabric peak gap for treesum(9) on 1x1?  Monkeypatches Cell.redex so its
pushes are reordered [x1..x_{n-1}, x0] (x0 popped first), expansions untouched."""
import sys; sys.path[:0] = ['.', 'tests']
from omega import progs, fabric
import test_mempress as tm
mode = sys.argv[1] if len(sys.argv) > 1 else "rtl"
C = fabric.Cell
orig_redex, orig_expand, orig_push = C.redex, C.expand, C.push
def push(self, a, b):
    buf = getattr(self, "_buf", None)
    if buf is not None: buf.append((a, b))
    else: orig_push(self, a, b)
def expand(self, *a, **k):
    save = getattr(self, "_buf", None); self._buf = None
    try: return orig_expand(self, *a, **k)
    finally: self._buf = save
def redex(self, a, b):
    self._buf = []
    try: r = orig_redex(self, a, b)
    finally:
        buf, self._buf = self._buf, None
    if buf and mode == "rtl": buf = buf[1:] + buf[:1]
    for x in buf: orig_push(self, *x)
    return r
C.push, C.expand, C.redex = push, expand, redex
b = progs.book('treesum', 9)
f = fabric.Fabric(b, 1, 1).run(); c = f.cells[(0, 0)]
print(mode, f.readback() == progs.expected('treesum', 9), {k: v for k, v in c.st.items() if k.startswith('max')})
