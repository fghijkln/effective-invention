import sys, time; sys.path[:0]=['.','tests']
import test_mempress as tm
from omega import progs, fabric
fabric.RTO=int(sys.argv[1]); seed=int(sys.argv[2])
name,N,W,H=("treesum",9,3,3)
book=progs.book(name,N); cells=tuple((x,y) for x in range(W) for y in range(H) if (x,y)!=(W-1,H-1))
f=fabric.Fabric(book,W,H,seed=seed,p_jitter=0.1,img=tm.ballast_img(book,W,H,1024,8,8,cells))
t=time.time()
try:
    f.run(); print("ok",f.cycles,f.interactions)
except Exception as e:
    print("ERR",e,f.cycles,f.interactions)
print("time",round(time.time()-t))
for k,c in sorted(f.cells.items()):
    print(k,"nfree",len(c.nfree),"vfree",len(c.vfree),"q",len(c.queue),"rs",c.rs is not None, c.rs_n,"ej",len(c.eject),"inq",{d:len(v) for d,v in c.inq.items()},"st",{s:c.st.get(s,0) for s in("interactions","park","requeue","offload","retry")})
print("msgs",f.msgs)
from omega.ports import *
nm={v:k for k,v in book.ids.items()}
from collections import Counter
cnt=Counter()
for k,c in f.cells.items():
    if c.rs: cnt[("park",k==(2,2),nm.get(label(c.rs[1])))]+=1
    for q in list(c.inq.values())+[c.eject]:
        for m in q:
            if m[0]==2: cnt[("msg",nm.get(label(m[3])))]+=1
print(cnt)
print({nm[i]:(len(book.defs[i].nodes),book.defs[i].nvars) for i in nm})
