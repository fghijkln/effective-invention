# step 20: per-cell work distribution, fabric model. usage: [knobs] diag.py case seed
import sys, json; sys.path[:0]=['.','tests']
import test_mempress as tm
from omega import progs, fabric
C={"t6":("treesum",6,3,3),"l20":("list",20,3,2),"f6":("fib",12,6,6)}
name,N,W,H=C[sys.argv[1]]; seed=int(sys.argv[2])
book=progs.book(name,N); cells=tuple((x,y) for x in range(W) for y in range(H) if (x,y)!=(W-1,H-1))
f=fabric.Fabric(book,W,H,seed=seed,p_jitter=0.1,img=tm.ballast_img(book,W,H,1024,8,8,cells)).run()
print("cycles",f.cycles)
for y in range(H):
    print(" | ".join("i%5d p%4d rq%4d mx%3d/%3d" % (f.cells[(x,y)].st["interactions"], f.cells[(x,y)].st.get("park",0), f.cells[(x,y)].st["requeue"],
          f.cells[(x,y)].st["max_nodes"], f.cells[(x,y)].st.get("max_vars",0)) for x in range(W)))
