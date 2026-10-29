"""Step 14 fabric-only semantic regression for the exploration knobs (bot_give, p_msg, governor shape):
every program on the fabric model vs the semantic reducer (readback + interaction count), on 1x1 / 2x2 /
3x2 / 4x4 / 8x8, with jitter / stall, scattered images and small (1024 / 256-slot) cells.
usage: test_fabric_var.py [cfg-name ...]   (default: all configs)"""
import sys, os, random, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from omega import progs, semantic, fabric

SUITE = [("fib", 12), ("sum", 100), ("fact", 12), ("list", 25), ("treesum", 7), ("treesum_direct", 9),
         ("sort", 15), ("qsort", 15), ("higher", 9)]
CFGS = {
    "dflt": dict(),                   # default (step 14 = s14c)
    "base": dict(s14=0),
    "mf": dict(p_msg=1.0),
    "bot1": dict(bot_give=1), "bot2": dict(bot_give=2), "bot3": dict(bot_give=3), "bot4": dict(bot_give=4),
    "bot3mf": dict(bot_give=3, p_msg=1.0),
    "gov_e16": dict(gov_e=16), "gov_l0": dict(gov_l0=1), "gov_nb": dict(gov_nb=1),
    "gov_k6": dict(gov_k=(0, 1, 2, 4, 8, 16), gov_l0=2), "gov_b50": dict(gov_b=50),
    "g3": dict(bot_give=3, fdepth=4, grad=3), "g3m3": dict(bot_give=3, fdepth=4, grad=3, dmin=3),
    "g7nr": dict(bot_give=3, grad=7, relay=0), "nb4l1": dict(gov_nb=4, gov_l0=1),
    "s14": dict(bot_give=3, fdepth=4, grad=3, dmin=3, gov_nb=4, gov_l0=1), "main_c": dict(main_at="c"),
    "s14b": dict(bot_give=3, fdepth=4, grad=3, dmin=3, gov_nb=5, gov_l0=1),
    "s14c": dict(bot_give=3, fdepth=4, gov_nb=5, gov_l0=1),
}


def main():
    want = [a for a in sys.argv[1:] if a in CFGS] or list(CFGS)
    rng = random.Random(14)
    n = fails = 0
    t0 = time.time()
    refs = {}
    for name, N in SUITE:
        b = progs.book(name, N)
        refs[name] = (b, semantic.result(b), progs.expected(name, N))
    for cname in want:
        kw = dict(CFGS[cname]); kw.setdefault("s14", 0 if cname != "dflt" else 1)
        for name, N in SUITE:
            b, ref, exp = refs[name]
            for (W, H) in ((1, 1), (2, 2), (3, 2), (4, 4), (8, 8)):
                for k in range(2 if W * H > 1 else 1):
                    seed = rng.randint(1, 10**6)
                    slots = 4096 if W * H == 1 else (256 if (k and W * H >= 4 and name not in ("sum", "fact")) else 1024)
                    scatter = rng.randint(0, 10**9) if k else None
                    kk = dict(kw)
                    if k:
                        kk.setdefault("p_msg", rng.choice([0.2, 0.5, 0.9]))
                    try:
                        mc = None
                        if kk.pop("main_at", None) == "c":
                            cl = [(x, y) for y in range(H) for x in range(W)]
                            i = cl.index((W // 2, H // 2)); mc = cl[i:] + cl[:i]
                        img = fabric.Image(b, W, H, slots, 4096, scatter=scatter, main_cells=mc)
                        f = fabric.Fabric(b, W, H, slots=slots, qdepth=4096, seed=seed, img=img,
                                          p_jitter=0.1 * k, p_stall=0.05 * k, **kk).run()
                        ok = f.readback() == exp and f.interactions == ref["interactions"] and not f.traps()
                        msg = f"{f.readback()[:30]} {f.interactions}/{ref['interactions']}"
                    except fabric.FabricError as e:
                        ok, msg = False, f"error {e}"
                    n += 1
                    if not ok:
                        fails += 1
                        print(f"FAIL {cname} {name}({N}) {W}x{H} k={k} slots={slots}: {msg}", flush=True)
        print(f"  {cname}: done ({n - fails}/{n} cumulative) {time.time() - t0:.0f}s", flush=True)
    print(f"fabric var tests: {n - fails}/{n} pass [{', '.join(want)}] {time.time() - t0:.0f}s")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
