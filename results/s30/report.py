"""Step 30: write results/s30/validation.md from val_*.jsonl and cert_table.json."""
import json, os, collections
H = os.path.dirname(os.path.abspath(__file__))
tab = json.load(open(os.path.join(H, "cert_table.json")))
out = ["# Step 30 RTL validation of the joint-load certificate with the task stack (SPEC §7.9)", "",
       "Every claimed run is a configuration `joint.certified` accepts (W_nodes, B_vars, hull, Q, engine margin, built QDEPTH). "
       "Sound = right answer and interaction count, +pcert and +tcert audits clean every cycle, live (n, v) inside W_nodes / B_vars "
       "and every hull line, stored task entries <= Q.  Uncertified runs carry no requirement.", ""]
for s in ("small", "hetero", "big", "boundary"):
    p = os.path.join(H, f"val_{s}.jsonl")
    if not os.path.exists(p): continue
    R = [json.loads(l) for l in open(p)]
    cl = [r for r in R if r.get("claim")]; un = [r for r in R if not r.get("claim")]
    out.append(f"## {s}: {len(R)} runs, {len(cl)} certified: {sum(r['sound'] for r in cl)}/{len(cl)} sound; "
               f"{len(un)} uncertified: {sum(bool(r.get('ok')) for r in un)} finished correctly, statuses {dict(collections.Counter(r.get('status') for r in un))}")
    if cl:
        out.append("- measured peak / bound: nodes %.4f max, vars %.4f max, task entries / Q %.5f max; largest mesh-wide task count %d, largest per-cell %d" % (
            max(r['live_peak'][0] / r['L'][0] for r in cl), max(r['live_peak'][1] / r['L'][1] for r in cl),
            max(r['tcert_peak'] / r['Q'] for r in cl), max(r['tcert_peak'] for r in cl), max(r['tcert_cell'] for r in cl)))
    out += ["", "| configuration | runs | certified | sound | status | cycles (min–max) | live peak max (n, v) | L (n, v) | task peak / Q |",
            "|---|---:|---:|---:|---|---|---|---|---|"]
    g = collections.OrderedDict()
    for r in R: g.setdefault(r["key"].rsplit(" k", 1)[0], []).append(r)
    for k, rs in g.items():
        cy = [r.get("cycles") or 0 for r in rs]
        lp = (max(r.get("live_peak", (0, 0))[0] for r in rs), max(r.get("live_peak", (0, 0))[1] for r in rs))
        L = rs[0].get("L"); L = tuple(L) if L else None
        out.append(f"| {k} | {len(rs)} | {sum(bool(r.get('claim')) for r in rs)} | {sum(bool(r.get('claim')) and r['sound'] for r in rs)} | "
                   f"{sorted({r.get('status') for r in rs})} | {min(cy)}–{max(cy)} | {lp} | {L} | {max(r.get('tcert_peak') or 0 for r in rs)} / {rs[0].get('Q')} |")
    out.append("")
out += ["## Smallest certified cell (slots) at the benchmark size: step 30 vs step 29", "",
        "| program (N) | hull | " + " | ".join(m for m in tab["fib"]["bench_min_S"]) + " |", "|---|---|" + "---:|" * len(tab["fib"]["bench_min_S"])]
for p, row in tab.items():
    s29 = row["s29_min_S"]
    out.append(f"| {p}({row['bench_N']}) | { {True: 'box', False: 'below box', None: 'worst case'}[row.get('hull_is_box')] } | " +
               " | ".join(f"{s:,} ({s29[m]:,})" for m, s in row["bench_min_S"].items()) + " |")
out += ["", "Cells: step 30 (step 29).  rgrad 3 unless named.", "",
        "## Largest certifiable N per configuration: step 30 vs step 29", "",
        "| program | " + " | ".join(m for m in tab["fib"]["nmax"]) + " |", "|---|" + "---:|" * len(tab["fib"]["nmax"])]
for p, row in tab.items():
    s29 = row["s29_nmax"]
    cells = []
    for m, n in row["nmax"].items():
        o = s29.get(m)
        cells.append(f"**{n}** ({o})" if n != o else f"{n} ({o})")
    out.append(f"| {p} | " + " | ".join(cells) + " |")
out += ["", "Step 30 (step 29); bold where step 30 certifies a larger N."]
open(os.path.join(H, "validation.md"), "w").write("\n".join(out) + "\n")
print("\n".join(out[-14:]))
