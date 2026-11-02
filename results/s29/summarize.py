"""Summary of results/s29/val_*.jsonl -> results/s29/validation.md"""
import json, collections, os
D = os.path.dirname(os.path.abspath(__file__))
out = ["# Step 29 RTL validation of the placement certificate", ""]
for which in ("small", "hetero", "big"):
    rs = [json.loads(l) for l in open(f"{D}/val_{which}.jsonl")]
    cl = [r for r in rs if r.get("claim")]
    nc = [r for r in rs if not r.get("claim")]
    snd = sum(r["sound"] for r in cl)
    rat = [(r["L"][0] / max(1, r["live_peak"][0]), r["L"][1] / max(1, r["live_peak"][1])) for r in cl if r.get("ok")]
    agree = all(r["cert"] == (not r["witness"]) for r in rs if "cert" in r and r.get("mesh") != "4x4" or "cert" in r and r["mesh"] == "4x4")
    out.append(f"## {which}: {len(rs)} runs, {len(cl)} certified: {snd}/{len(cl)} sound; {len(nc)} uncertified: {sum(r.get('ok', False) for r in nc)} finished correctly, "
               f"{sum(1 for r in nc if (r.get('pcert_viol') or 0) > 0)} with audit count > 0")
    if rat: out.append(f"- L / measured live peak: nodes {min(a for a, b in rat):.1f}–{max(a for a, b in rat):.0f}×, vars {min(b for a, b in rat):.1f}–{max(b for a, b in rat):.0f}×")
    out.append(f"- certificate = no brute-force witness on every run: {all(r['cert'] == (not r['witness']) for r in rs if 'cert' in r and r['mesh'] in ('2x2', '3x3', '4x4'))}")
    g = collections.defaultdict(list)
    for r in cl: g[r["key"].rsplit(" k", 1)[0] if which != "hetero" else r["key"].split(" ")[0] if not r["key"].startswith("rand") else "random"].append(r)
    out.append("")
    out.append("| configuration | runs | sound | cycles (min–max) | live peak max (n, v) | L (n, v) | largest per-cell peak (n, v) |")
    out.append("|---|---:|---:|---|---|---|---|")
    for k, v in g.items():
        cy = [r["cycles"] for r in v if r.get("cycles")]
        out.append(f"| {k} | {len(v)} | {sum(r['sound'] for r in v)} | {min(cy) if cy else '-'}–{max(cy) if cy else '-'} | "
                   f"({max(r['live_peak'][0] for r in v)}, {max(r['live_peak'][1] for r in v)}) | {tuple(v[0]['L'])} | "
                   f"({max(r['cell_peak_max'][0] for r in v)}, {max(r['cell_peak_max'][1] for r in v)}) |")
    out.append("")
open(f"{D}/validation.md", "w").write("\n".join(out) + "\n")
print("\n".join(out))
