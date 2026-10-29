"""Differential fuzz: random nets, RTL mesh under random schedules vs the semantic reducer.

Each case: random book (omega/randnet.py), rejected if it does not normalise within the fuel; the
semantic reducer gives (readback, interactions, node count); the RTL runs it on a mesh shape picked
from CONFIGS with a random arbitration seed, link jitter, engine stall rate, message/task priority
and a random scatter of @main's nodes over the cells.  All three observables must match.
usage: fuzz_rtl.py START COUNT [--mut HEX] [--out FILE]
"""
import sys, os, json, random, time, argparse
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from omega import randnet, semantic, fabric, rtl

CONFIGS = [(1, 1), (2, 2), (4, 4), (3, 2), (1, 4)]


def case(i, mut=0, big=False):
    if big:
        g = random.Random(i ^ 0x5EED)
        b = randnet.gen_book(i, ndefs=g.randint(3, 8), size=g.randint(20, 60), maxdepth=6, nrdx=10, refs=0.35)
    else:
        b = randnet.gen_book(i)
    try:
        ref = semantic.result(b, seed=i, fuel=20000 if big else 5000)
    except semantic.OutOfFuel:
        return None
    if big and ref["interactions"] < 30:
        return None
    rng = random.Random(i * 7919 + 1)
    W, H = CONFIGS[i % len(CONFIGS)]
    knobs = dict(seed=rng.randint(1, 2**31), jitter=rng.choice([0, 0, 30, 80, 160]), stall=rng.choice([0, 20, 60]),
                 pmsg=rng.randint(0, 255))
    img = fabric.Image(b, W, H, 1024, 1024, scatter=rng.randint(0, 10**9) if rng.random() < 0.7 else None)
    # step 11 spawn policy, drawn from its own stream (the step-10 knob sequence is unchanged)
    sp = random.Random(i * 104729 + 7)
    knobs["spawn"] = (sp.choice([-1, 0, 1, 3, 8, 8, 32]), sp.choice([0, 1, 1]))
    knobs["link_local"] = sp.choice([0, 1, 1])        # step 12 local-first link orientation
    # step 13 producer threshold and message-budget governor (own stream again)
    s13 = random.Random(i * 15485863 + 13)
    knobs["spawn"] += (fabric.SPAWN_K2, s13.choice([-1, 0, 2, 4, 4, 16]), s13.choice([0, 0, 10, 50, 200]))
    knobs["s14"] = random.Random(i * 32452843 + 14).choice([0, 1, 1])   # step 14 fork deque on / off
    r = rtl.run(b, W, H, img=img, mut=mut, maxcycles=2_000_000, **knobs)
    ok = (r["readback"] == ref["readback"] and r["interactions"] == ref["interactions"]
          and r["node_count"] == ref["nodes"] and r["status"] == 0)
    return dict(i=i, W=W, H=H, ok=ok, knobs=knobs, interactions=ref["interactions"], cycles=r.get("cycles"),
                got=r["readback"][:200], want=ref["readback"][:200], got_i=r["interactions"], got_n=r["node_count"],
                want_n=ref["nodes"], status=r["status"], msgs=r["msgs"])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("start", type=int); ap.add_argument("count", type=int)
    ap.add_argument("--mut", default="0"); ap.add_argument("--out", default=None)
    ap.add_argument("--stop-on-fail", action="store_true")
    ap.add_argument("--big", action="store_true", help="larger random books (3-8 defs, 20-60 nodes per def)")
    a = ap.parse_args()
    mut = int(a.mut, 16)
    n = fails = skipped = 0
    out = open(a.out, "a") if a.out else None
    t = time.time()
    i = a.start
    while n < a.count:
        res = case(i, mut, a.big)
        i += 1
        if res is None:
            skipped += 1; continue
        n += 1
        if out: out.write(json.dumps(res) + "\n"); out.flush()
        if not res["ok"]:
            fails += 1
            print("FAIL", json.dumps(res))
            if a.stop_on_fail: break
    print(f"fuzz{' (big)' if a.big else ''} {a.start}..{i-1}: {n - fails}/{n} pass, {skipped} rejected (diverging), {time.time()-t:.0f}s")
    sys.exit(1 if fails else 0)
