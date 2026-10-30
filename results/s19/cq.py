import sys; sys.path[:0]=['.','tests']
import test_mempress as tm
from omega import progs, fabric
from omega.ports import *
name,N,W,H=("treesum",9,3,3)
book=progs.book(name,N); cells=tuple((x,y) for x in range(W) for y in range(H) if (x,y)!=(W-1,H-1))
nm={v:k for k,v in book.ids.items()}
def d(p): 
    t=tag(p); s=TAG_NAMES[t] if t<9 else str(t)
    if t==REF: s+=":"+nm[label(p)]
    elif t>=VAR and t!=NUM and t!=ERA: s+=str(addr_xy(payload(p)))
    return s
rto,seed,T=map(int,sys.argv[1:4]); fabric.RTO=rto
f=fabric.Fabric(book,W,H,seed=seed,p_jitter=0.1,img=tm.ballast_img(book,W,H,1024,8,8,cells))
for _ in range(T): f.step()
for k,c in sorted(f.cells.items()):
    q=list(c.queue); print(k,len(q),"bottom:",[(kk,d(a),d(b)) for kk,a,b in q[:8]])
    if hasattr(c.queue,'f'): print("   fork deque",[(kk,d(a),d(b)) for kk,a,b in c.queue.f])
