"""Area / Fmax comparison of a TACHYON-Omega mesh with one TACHYON-128 core (step 2, synth/flow.py).

Inputs: synth/out/{omega_cell,omega_rom,tx_core}/summary.json (Nangate45 + fakeram45-density estimate
+ OpenSTA pre-layout), fib(20) cycles from results/bench_<tag>.json (default bench_c2x2p1.json: 2x2
cells per ROM, one port) and TACHYON-128 v6 fib(20) cycles (296,931, cpu128/README.md).
Mesh area counts every cell plus every cluster ROM the mesh actually needs (ceil(W/2) x ceil(H/2));
"per cell" divides that by the number of cells (so a 1x1 mesh pays a whole ROM).
Writes results/area_fmax.md and results/area_fmax.json.
usage: python3 bench/area_table.py [--bench results/bench_c2x2p1.json]
"""
import json, math, os, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TX_FIB20 = 296931


def load(d):
    return json.load(open(os.path.join(ROOT, "synth", "out", d, "summary.json")))


def main():
    bpath = sys.argv[sys.argv.index("--bench") + 1] if "--bench" in sys.argv else "results/bench_c2x2p1.json"
    bench = json.load(open(os.path.join(ROOT, bpath)))
    cell, rom, tx = load("omega_cell"), load("omega_rom"), load("tx_core")
    f_cell = min(cell["fmax_mhz"], rom["fmax_mhz"])
    rows = [dict(machine="TACHYON-128 tx_core (v6 cycles)", cells=1, roms=0, area=tx["total_area_um2"],
                 std=tx["std_cell_area_um2"], mem=tx["mem_area_um2"], fmax=tx["fmax_mhz"], cycles=TX_FIB20)]
    for mesh in ("1x1", "2x2", "4x4", "8x8"):
        r = [b for b in bench if b["prog"] == "fib(20)" and b["mesh"] == mesh]
        if not r: continue
        w, h = map(int, mesh.split("x"))
        n, nr = w * h, math.ceil(w / 2) * math.ceil(h / 2)
        rows.append(dict(machine=f"TACHYON-Omega {mesh}", cells=n, roms=nr,
                         area=n * cell["total_area_um2"] + nr * rom["total_area_um2"],
                         std=n * cell["std_cell_area_um2"] + nr * rom["std_cell_area_um2"],
                         mem=n * cell["mem_area_um2"] + nr * rom["mem_area_um2"], fmax=f_cell, cycles=r[0]["cycles"]))
    base = rows[0]
    for r in rows:
        r["time_us"] = r["cycles"] / r["fmax"]
        r["area_x_cycles"] = r["area"] * r["cycles"]
        r["area_x_time"] = r["area"] * r["time_us"]
        r["std_x_cycles"] = r["std"] * r["cycles"]
        r["per_cell_area"] = r["area"] / r["cells"]
    for r in rows:
        for k in ("time_us", "area_x_cycles", "area_x_time", "std_x_cycles"):
            r[k + "_rel"] = r[k] / base[k]
    mm = lambda a: f"{a / 1e6:.3f}"
    out = ["| machine | cells + ROMs | area mm² (std cell / memory) | per cell mm² | Fmax MHz | fib(20) cycles | time µs | "
           "area × cycles (vs T-128) | std-cell area × cycles (vs T-128) | area × time (vs T-128) |",
           "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in rows:
        out.append(f"| {r['machine']} | {r['cells']} + {r['roms']} | {mm(r['area'])} ({mm(r['std'])} / {mm(r['mem'])}) | "
                   f"{mm(r['per_cell_area'])} | {r['fmax']:.1f} | {r['cycles']:,} | {r['time_us']:,.0f} ({r['time_us_rel']:.2f}×) | "
                   f"{r['area_x_cycles_rel']:.2f}× | {r['std_x_cycles_rel']:.2f}× | {r['area_x_time_rel']:.2f}× |")
    hdr = (f"Designs (synth/out/*/summary.json): omega_cell std cell {cell['std_cell_area_um2']:,.0f} µm² + memory "
           f"{cell['mem_area_um2']:,.0f} µm² ({cell['mem_bits']:,} bits), Fmax {cell['fmax_mhz']:.1f} MHz; omega_rom "
           f"(4 cells) std cell {rom['std_cell_area_um2']:,.0f} µm² + memory {rom['mem_area_um2']:,.0f} µm² "
           f"({rom['mem_bits']:,} bits), Fmax {rom['fmax_mhz']:.0f} MHz; tx_core std cell {tx['std_cell_area_um2']:,.0f} µm² "
           f"+ memory {tx['mem_area_um2']:,.0f} µm² ({tx['mem_bits']:,} bits), Fmax {tx['fmax_mhz']:.1f} MHz. "
           f"Omega cycles: {bpath}.\n\n")
    open(os.path.join(ROOT, "results", "area_fmax.md"), "w").write(hdr + "\n".join(out) + "\n")
    json.dump(rows, open(os.path.join(ROOT, "results", "area_fmax.json"), "w"), indent=1)
    print(hdr + "\n".join(out))


if __name__ == "__main__":
    main()
