import sys; sys.path[:0]=['.','tests']
import test_mempress as tm
from omega import progs, fabric
from omega.ports import *
from collections import Counter
fabric.RTO=int(sys.argv[1]); seed=int(sys.argv[2]); T=int(sys.argv[3])
name,N,W,H=("treesum",9,3,3)
book=progs.book(name,N); cells=tuple((x,y) for x in range(W) for y in range(H) if (x,y)!=(W-1,H-1))
f=fabric.Fabric(book,W,H,seed=seed,p_jitter=0.1,img=tm.ballast_img(book,W,H,1024,8,8,cells))
for _ in range(T): f.step()
C=f.cells[(2,2)]
nm={v:k for k,v in book.ids.items()}
TN={getattr(sys.modules['omega.ports'],n):n for n in dir(sys.modules['omega.ports']) if n.isupper() and isinstance(getattr(sys.modules['omega.ports'],n),int) and getattr(sys.modules['omega.ports'],n)<16}
cv=Counter()
for s,v in enumerate(C.vars):
    if v is None or C.vown[s]==14: continue
    t=tag(v)
    loc = addr_xy(payload(v)) if t not in (NONE,NUM,ERA,REF) else None
    cv[(TN.get(t,t), nm.get(label(v)) if t==REF else None, loc)]+=1
print(cv.most_common(15))
cn=Counter()
for s,e in enumerate(C.nodes):
    if e is None or C.nown[s]==14: continue
    cn[tuple(TN.get(tag(p),tag(p)) for p in e)]+=1
print(cn.most_common(10))
for k,c in sorted(f.cells.items()):
  if k!=(2,2): print(k,[ (TN.get(tag(a)),nm.get(label(a)) if tag(a)==REF else '',TN.get(tag(b))) for (kk,a,b) in list(c.queue)[:6]], c.rs and (TN.get(tag(c.rs[1])),nm.get(label(c.rs[1]))))
