# step 22 RTL: treesum(9) 3x3, ballast 8/8 in 8 cells, corner keeps K free slots; lm mode via fabric.ADM
# usage (from a tree with the step-22 RTL): rtl_cex.py ADM K seeds
import sys, json; sys.path[:0]=['.','tests']
import test_mempress as tm
from omega import progs, fabric, rtl
from omega.ports import mk, ERA, NONE
fabric.ADM=int(sys.argv[1]); K=int(sys.argv[2]); s0,s1=map(int,sys.argv[3].split('-'))
b=progs.book("treesum",9); want=progs.expected("treesum",9)
bad=[]; cyc=[]
for s in range(s0,s1+1):
    i=tm.ballast_img(b,3,3,1024,8,8,tuple((x,y) for x in range(3) for y in range(3) if (x,y)!=(2,2)))
    c=(2,2); fn=[t for t in range(1024) if i.nodes[c][t] is None]; fv=[t for t in range(1024) if i.vars[c][t] is None]
    for t in fn[K:]: i.nodes[c][t]=[mk(ERA),mk(ERA)]; i.nown[c][t]=14
    for t in fv[K:]: i.vars[c][t]=mk(NONE); i.vown[c][t]=14
    r=rtl.run(b,3,3,img=i,seed=s,jitter=30,maxcycles=400_000,timeout=900)
    if r["status"]!=0 or r["readback"]!=want: bad.append((s,r["status"],r["interactions"]))
    else: cyc.append(r["cycles"])
print(json.dumps({"adm":fabric.ADM,"K":K,"seeds":sys.argv[3],"stuck":bad,"n":s1-s0+1,"cycles":round(sum(cyc)/len(cyc)) if cyc else None}),flush=True)
