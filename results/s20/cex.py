# step 20 B: does the default stall when total memory would suffice for a depth-first run?
# treesum(9): 3x3, ballast cells keep 8/8, the corner keeps K/K.  1x1 with K/K as the sequential reference.
# usage: [knobs] cex.py K s0-s1
import sys, json; sys.path[:0]=['.','tests']
import test_mempress as tm
from omega import progs, fabric
K=int(sys.argv[1]); s0,s1=[int(v) for v in sys.argv[2].split('-')]
book=progs.book("treesum",9)
def img(W,H):
    i=tm.ballast_img(book,W,H,1024,8,8,tuple((x,y) for x in range(W) for y in range(H) if (x,y)!=(W-1,H-1)))
    return tm.ballast_img.__wrapped__(i) if False else i
out={"K":K,"rhi":__import__("os").environ.get("RHI"),"knobs":{k:v for k,v in __import__('os').environ.items() if k.startswith("OMEGA_")}}
# 1x1 reference with K free slots
i1=tm.ballast_img(book,1,1,1024,K,K,((0,0),))
try: f=fabric.Fabric(book,1,1,seed=1,img=i1).run(); out["1x1"]=f.cycles
except Exception as e: out["1x1"]="fail: "+str(e)[:40]
bad=[];cyc=[]
for s in range(s0,s1+1):
    i=tm.ballast_img(book,3,3,1024,8,8,tuple((x,y) for x in range(3) for y in range(3) if (x,y)!=(2,2)))
    # corner: keep K of its free slots
    c=(2,2); fn=[t for t in range(1024) if i.nodes[c][t] is None]; fv=[t for t in range(1024) if i.vars[c][t] is None]
    from omega.ports import mk, ERA, NONE
    for t in fn[K:]: i.nodes[c][t]=[mk(ERA),mk(ERA)]; i.nown[c][t]=14
    for t in fv[K:]: i.vars[c][t]=mk(NONE); i.vown[c][t]=14
    import os
    try:
        f=fabric.Fabric(book,3,3,seed=s,p_jitter=0.1,img=i)
        if os.environ.get("RHI"):
            for c in f.cells.values(): c.room_hi, c.room_lo = int(os.environ["RHI"]), int(os.environ["RLO"]); c.update_roomy()
        f.run(); cyc.append(f.cycles)
    except Exception as e: bad.append(s)
out["stuck"]=bad; out["n"]=s1-s0+1; out["cycles"]=round(sum(cyc)/len(cyc)) if cyc else None
print(json.dumps(out),flush=True)
