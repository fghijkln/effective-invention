"""Benchmarks on the RTL mesh (Verilator, cycle accurate): interactions, cycles, speed-up vs 1x1,
message traffic, cell utilisation.  Writes results/bench.json and results/bench.md.
usage: bench.py [--quick] [--8x8] [--progs fib:20,treesum:9] [--tag NAME] [--cluster 2x2:1]"""
import sys, os, json, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from omega import progs, semantic, rtl

FULL = [("fib", 20), ("treesum_direct", 14), ("treesum", 9), ("qsort", 40), ("list", 120), ("sum", 1000), ("fact", 12)]
QUICK = [("fib", 15), ("treesum_direct", 10), ("treesum", 8), ("qsort", 20), ("list", 60), ("sum", 200), ("fact", 12)]
SHAPES = [(1, 1), (2, 2), (4, 4)]


def main():
    work = QUICK if "--quick" in sys.argv else FULL
    if "--progs" in sys.argv:
        work = [(p.split(":")[0], int(p.split(":")[1])) for p in sys.argv[sys.argv.index("--progs") + 1].split(",")]
    shapes = SHAPES + ([(8, 8)] if "--8x8" in sys.argv else [])
    if "--cluster" in sys.argv:          # cluster ROM: CWxCH cells share one ROM with P read ports
        shape, _, ports = sys.argv[sys.argv.index("--cluster") + 1].partition(":")
        rtl.CLUSTER = tuple(int(t) for t in shape.split("x")) + (int(ports or 1),)
    out = []
    for name, n in work:
        b = progs.book(name, n)
        ref = semantic.result(b, order="lifo")
        exp = progs.expected(name, n)
        assert ref["readback"] == exp, (name, ref["readback"], exp)
        base = None
        for W, H in shapes:
            t = time.time()
            r = rtl.run(b, W, H, maxcycles=200_000_000, timeout=3600)
            slots = 1024
            if r["status"] != 0 and (W, H) == (1, 1):
                # the program does not fit one 1024-slot cell: sequential baseline on a 4096-slot cell
                slots = 4096
                r = rtl.run(b, W, H, slots=4096, maxcycles=200_000_000, timeout=3600)
            ok = r["readback"] == exp and r["interactions"] == ref["interactions"]
            cyc = r["cycles"]
            base = base or cyc
            row = dict(cluster="%dx%d:%d" % rtl.CLUSTER, prog=f"{name}({n})", mesh=f"{W}x{H}" + ("*" if slots != 1024 else ""), ok=ok, interactions=r["interactions"], cycles=cyc,
                       speedup=base / cyc, ipc=r["interactions"] / cyc, util=r["util"],
                       msg_link=r["msgs"]["msg_link"], msg_node=r["msgs"]["msg_node"], msg_spawn=r["msgs"]["msg_spawn"],
                       msgs_per_inter=sum(r["msgs"].values()) / max(1, r["interactions"]),
                       max_cell_inter=max(c["interactions"] for c in r["cells"].values()),
                       min_cell_inter=min(c["interactions"] for c in r["cells"].values()),
                       maxq=max(c["maxq"] for c in r["cells"].values()), status=r["status"],
                       peak_nodes=max(c["peak_nodes"] for c in r["cells"].values()),
                       peak_vars=max(c["peak_vars"] for c in r["cells"].values()), wall=time.time() - t)
            out.append(row)
            print(json.dumps(row), flush=True)
    os.makedirs("results", exist_ok=True)
    tag = "_quick" if "--quick" in sys.argv else ""
    if "--tag" in sys.argv:
        tag = "_" + sys.argv[sys.argv.index("--tag") + 1]
    json.dump(out, open(f"results/bench{tag}.json", "w"), indent=1)
    with open(f"results/bench{tag}.md", "w") as f:
        f.write("| program | mesh | ok | interactions | cycles | speed-up vs 1x1 | interactions/cycle | cell utilisation | LINK msgs | NODE msgs | SPAWN msgs | msgs/interaction | busiest / idlest cell (interactions) | peak nodes / vars in one cell |\n")
        f.write("|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|\n")
        for r in out:
            f.write(f"| {r['prog']} | {r['mesh']} | {'yes' if r['ok'] else 'NO'} | {r['interactions']:,} | {r['cycles']:,} | {r['speedup']:.2f}x | {r['ipc']:.3f} | {100*r['util']:.0f}% | {r['msg_link']:,} | {r['msg_node']:,} | {r['msg_spawn']:,} | {r['msgs_per_inter']:.2f} | {r['max_cell_inter']:,} / {r['min_cell_inter']:,} | {r['peak_nodes']} / {r['peak_vars']} |\n")


if __name__ == "__main__":
    main()
