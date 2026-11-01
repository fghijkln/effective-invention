import sys, time; sys.path.insert(0, "."); sys.path.insert(0, "tests")
from omega import admission, adm_rtl, progs
TINY = [("fib", 5), ("treesum_direct", 4), ("fact", 12), ("sum", 10), ("fib", 4), ("treesum_direct", 3)]
sp = TINY * 2
jobs = [admission.Job(f"{n}({N})", progs.source(n, N), k % 15) for k, (n, N) in enumerate(sp)]
t = time.time()
r = adm_rtl.run_admitted(jobs, 2, 2, 150)
print(r["status"], r["cycles"], r["interactions"], r.get("max_reserved"), r["budget"], r.get("peak_live"), r.get("nviol"), r["blocked"], time.time() - t)
for j, (n, N) in zip(r["jobs"], sp): print(j["name"], j["state"], j["start"], j["end"], j["result"], progs.expected(n, N))
print(r["events"][:6])
jobs2 = [admission.Job(f"{n}({N})", progs.source(n, N), k % 15) for k, (n, N) in enumerate(sp)]
sch = admission.Scheduler(jobs2, 2, 2, 150, admit=True); rp = sch.run(audit=True)
print("py", rp["status"], rp["cycles"], rp["interactions"], rp["max_reserved"], rp["budget"], rp["violation"])
for j in rp["jobs"]: print(" ", j["name"], j["state"], j["need"], j["start"], j["end"], j["result"])
