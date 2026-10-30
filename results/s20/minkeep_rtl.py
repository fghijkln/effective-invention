# step 20: smallest free-slot count with which fib(10) finishes on a 1x1 RTL mesh (mutant 51's kill test)
import sys; sys.path[:0]=['.','tests']
import test_mempress as tm
from omega import progs, rtl
name,N=sys.argv[1],int(sys.argv[2]); b=progs.book(name,N); want=progs.expected(name,N)
def ok(K, mut=0):
    r=rtl.run(b,1,1,img=tm.ballast_img(b,1,1,1024,K,K,((0,0),)),maxcycles=200_000,mut=mut); return r["status"]==0 and r["readback"]==want
lo,hi=int(sys.argv[3]),int(sys.argv[4])
while lo<hi:
    m=(lo+hi)//2
    if ok(m): hi=m
    else: lo=m+1
print(name,N,"rtl min keep",lo,ok(lo),ok(lo-1),"mutant51 at min:",ok(lo,1<<51))
