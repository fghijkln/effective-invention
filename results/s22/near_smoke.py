import sys; sys.path[:0]=['.','tests']
from omega import progs, rtl, fabric, semantic
import test_mempress as tm
b=progs.book("treesum",9); want=progs.expected("treesum",9)
for lm in (0,2):
    fabric.LM=lm
    r=rtl.run(b,3,3,img=tm.near_img(b,3,3,500),seed=9,jitter=30,maxcycles=400_000,timeout=900)
    print("RTL lm",lm,"status",r["status"],"ok",r["readback"]==want,"cycles",r["cycles"],flush=True)
