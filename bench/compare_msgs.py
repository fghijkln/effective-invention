"""Base vs new benchmark table (cycles, speed-up vs 1x1, msgs/interaction, utilisation, LINK/NODE/SPAWN).
usage: compare_msgs.py BASE.json NEW.json OUT.md [title]"""
import sys, json
base = {(r["prog"], r["mesh"].rstrip("*")): r for r in json.load(open(sys.argv[1]))}
new = {(r["prog"], r["mesh"].rstrip("*")): r for r in json.load(open(sys.argv[2]))}
title = sys.argv[4] if len(sys.argv) > 4 else "step 10 (base) vs new"
rows = ["| program | mesh | cycles base → new | Δ cycles | speed-up vs 1x1 base → new | msgs/interaction base → new | util base → new | LINK / NODE / SPAWN base | LINK / NODE / SPAWN new |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
for k, b in base.items():
    n = new.get(k)
    if not n: continue
    d = (n["cycles"] - b["cycles"]) / b["cycles"] * 100
    ok = "" if (b["ok"] and n["ok"]) else " **(result mismatch)**"
    rows.append(f"| {k[0]} | {k[1]} | {b['cycles']:,} → {n['cycles']:,}{ok} | {d:+.1f}% | {b['speedup']:.2f}x → {n['speedup']:.2f}x | "
                f"{b['msgs_per_inter']:.3f} → **{n['msgs_per_inter']:.3f}** | {100*b['util']:.0f}% → {100*n['util']:.0f}% | "
                f"{b['msg_link']:,} / {b['msg_node']:,} / {b['msg_spawn']:,} | {n['msg_link']:,} / {n['msg_node']:,} / {n['msg_spawn']:,} |")
open(sys.argv[3], "w").write(f"### {title}\n\n" + "\n".join(rows) + "\n")
print("\n".join(rows))
