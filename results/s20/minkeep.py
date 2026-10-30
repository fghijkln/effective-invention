# step 20: smallest free-slot count with which a 1x1 fabric finishes (for mutant 51's kill test)
import sys; sys.path[:0]=['.','tests']
import test_mempress as tm
from omega import progs, fabric
name,N=sys.argv[1],int(sys.argv[2]); b=progs.book(name,N)
def ok(K):
    try: fabric.Fabric(b,1,1,seed=1,img=tm.ballast_img(b,1,1,1024,K,K,((0,0),))).run(); return True
    except Exception: return False
lo,hi=1,1024
while lo<hi:
    m=(lo+hi)//2
    if ok(m): hi=m
    else: lo=m+1
print(name,N,"min keep",lo, ok(lo), ok(lo-1))
