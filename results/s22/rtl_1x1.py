import sys; sys.path[:0]=['.','tests']
import test_mempress as tm
from omega import progs, rtl
b=progs.book("treesum",9)
for K in map(int, sys.argv[1].split(',')):
    r=rtl.run(b,1,1,img=tm.ballast_img(b,1,1,1024,K,K,((0,0),)),maxcycles=400_000)
    c=r["cells"][(0,0)] if (0,0) in r["cells"] else list(r["cells"].values())[0]
    print("1x1 K",K,"status",r["status"],"inter",r["interactions"],"cycles",r["cycles"],"free n/v at end",c.get("free_nodes"),c.get("free_vars"),flush=True)
