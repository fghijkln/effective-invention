import sys, os; sys.path[:0]=['.','tests']
from omega import progs, rtl, fabric
import test_mempress as tm
b=progs.book("fib",10)
for adm in (0,8,24):
    fabric.ADM=adm
    r=rtl.run(b,2,2,seed=1); print("adm",adm,"fib(10) 2x2",r["status"],r["readback"],r["cycles"],flush=True)
