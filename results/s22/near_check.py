import sys; sys.path[:0]=['.','tests']
import test_mempress as tm
from omega import fabric
print("lm", fabric.LM, "near:", tm.run_near(True, 0, True), flush=True)
