"""Direct (non-extrapolated) joint loads for the benchmark sizes, to check the fitted closed forms of cert_table.py."""
import sys, json, time; sys.setrecursionlimit(1000000)
from omega import joint, progs
out = {}
for name, N in (("treesum_direct", 14), ("fib", 20), ("treesum", 9), ("list", 120), ("higher", 100), ("sum", 1000)):
    t = time.time(); L = joint.loads(progs.book(name, N))
    out[f"{name}({N})"] = {"W_nodes": L["W_nodes"], "B_vars": L["B_vars"], "atoms": L["atoms"], "Q": L["Q"], "events": L["events"],
                           "hull": [[str(l), str(p)] for l, p in L["hull"]], "secs": round(time.time() - t, 1)}
    print(name, N, out[f"{name}({N})"], flush=True)
    json.dump(out, open("results/s30/direct.json", "w"), indent=1)
