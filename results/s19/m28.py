import sys, test_mempress as tm
from omega import fabric
q = sys.argv[1] == "quick"
if len(sys.argv) > 2: fabric.RTO, fabric.RGRAD = int(sys.argv[2]), int(sys.argv[3])
print(fabric.RTO, fabric.RGRAD)
print(tm.run_cases(True, 1 << 28, verbose=True, quick=q))
