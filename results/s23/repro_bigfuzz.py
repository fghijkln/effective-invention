import sys, os, json, random
sys.path.insert(0, "/workspace/work/omega"); sys.path.insert(0, "/workspace/work/omega/tests")
from omega import randnet, semantic, fabric, rtl
i = 3420; ilr = int(sys.argv[1]); slots = int(sys.argv[2]); q = int(sys.argv[3])
fabric.ILR = ilr
g = random.Random(i ^ 0x5EED)
b = randnet.gen_book(i, ndefs=g.randint(3, 8), size=g.randint(20, 60), maxdepth=6, nrdx=10, refs=0.35)
ref = semantic.result(b, seed=i, fuel=20000)
rng = random.Random(i * 7919 + 1)
knobs = dict(seed=rng.randint(1, 2**31), jitter=rng.choice([0, 0, 30, 80, 160]), stall=rng.choice([0, 20, 60]), pmsg=rng.randint(0, 255))
img = fabric.Image(b, 1, 1, slots, q, scatter=rng.randint(0, 10**9) if rng.random() < 0.7 else None)
sp = random.Random(i * 104729 + 7)
knobs["spawn"] = (sp.choice([-1, 0, 1, 3, 8, 8, 32]), sp.choice([0, 1, 1])); knobs["link_local"] = sp.choice([0, 1, 1])
s13 = random.Random(i * 15485863 + 13)
knobs["spawn"] += (fabric.SPAWN_K2, s13.choice([-1, 0, 2, 4, 4, 16]), s13.choice([0, 0, 10, 50, 200]))
knobs["s14"] = random.Random(i * 32452843 + 14).choice([0, 1, 2, 2])
r = rtl.run(b, 1, 1, img=img, slots=slots, qdepth=q, maxcycles=4_000_000, **knobs)
print(json.dumps(dict(ilr=ilr, slots=slots, q=q, status=r["status"], err=r.get("err"), cyc=r.get("cycles"), inter=r["interactions"], want_i=ref["interactions"],
  ok=r["readback"] == ref["readback"], nodes=r["node_count"], want_n=ref["nodes"], cells=str(r.get("cells"))[:300])))
