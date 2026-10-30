import sys; sys.path[:0]=['.','tests']
import test_mempress as tm
from omega import progs, fabric
from omega.ports import *
from collections import Counter
fabric.RTO=int(sys.argv[1]); seed=int(sys.argv[2]); T=int(sys.argv[3])
name,N,W,H=("treesum",9,3,3)
book=progs.book(name,N); cells=tuple((x,y) for x in range(W) for y in range(H) if (x,y)!=(W-1,H-1))
nm={v:k for k,v in book.ids.items()}
E=Counter(); F=Counter()
oe=fabric.Cell.expand
def ex(self,refp,x,forwarded=False):
    d=self.fab.book[label(refp)]
    if len(self.nfree)>=len(d.nodes) and len(self.vfree)>=d.nvars: E[((self.x,self.y)==(2,2),nm[label(refp)])]+=1
    else: F[((self.x,self.y),nm[label(refp)])]+=1
    return oe(self,refp,x,forwarded)
fabric.Cell.expand=ex
f=fabric.Fabric(book,W,H,seed=seed,p_jitter=0.1,img=tm.ballast_img(book,W,H,1024,8,8,cells))
for _ in range(T): f.step()
print("expanded (corner?,def):",sorted(E.items()))
print("no-room attempts:",F.most_common(12))
