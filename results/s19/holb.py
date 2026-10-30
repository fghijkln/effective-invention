import sys; sys.path[:0]=['.','tests']
import test_mempress as tm
from omega import progs, fabric
from collections import Counter
name,N,W,H=("treesum",9,3,3)
book=progs.book(name,N); cells=tuple((x,y) for x in range(W) for y in range(H) if (x,y)!=(W-1,H-1))
for rto,seed in [(8,1),(8,2),(32,1),(32,2),(32,3)]:
    fabric.RTO=rto
    f=fabric.Fabric(book,W,H,seed=seed,p_jitter=0.1,img=tm.ballast_img(book,W,H,1024,8,8,cells))
    for _ in range(3000): f.step()
    print(rto,seed,"holb",{k:c.st.get("holb",0) for k,c in f.cells.items() if c.st.get("holb",0)},"park",sum(c.st.get("park",0) for c in f.cells.values()),"msgs",f.msgs,
          "nfree",{k:len(c.nfree) for k,c in f.cells.items()},"vfree",{k:len(c.vfree) for k,c in f.cells.items() if k!=(2,2)},flush=True)
