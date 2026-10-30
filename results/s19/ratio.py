import sys; sys.path[:0]=['.','tests']
import test_mempress as tm
from omega import progs, fabric
from omega.ports import *
from collections import Counter
name,N,W,H=("treesum",9,3,3)
book=progs.book(name,N); cells=tuple((x,y) for x in range(W) for y in range(H) if (x,y)!=(W-1,H-1))
nm={v:k for k,v in book.ids.items()}
E=Counter()
oe=fabric.Cell.expand
def ex(self,refp,x,forwarded=False):
    d=self.fab.book[label(refp)]
    if len(self.nfree)>=len(d.nodes) and len(self.vfree)>=d.nvars: E[nm[label(refp)][:4]]+=1
    return oe(self,refp,x,forwarded)
fabric.Cell.expand=ex
for rto in map(int,sys.argv[1].split(',')):
  fabric.RTO=rto
  for seed in range(1,int(sys.argv[2])+1):
    E.clear()
    f=fabric.Fabric(book,W,H,seed=seed,p_jitter=0.1,img=tm.ballast_img(book,W,H,1024,8,8,cells))
    for _ in range(3000): f.step()
    C=f.cells[(2,2)]
    print(rto,seed,"tsum",E['tsum'],"gen",E['gen'],"corner vars",1024-len(C.vfree),flush=True)
