"""Step 26: memory-bound admission control in the RTL (rtl/omega_adm.sv, SPEC §7.5) - the host side.

`run_admitted(jobs, W, H, S)` builds an *empty* image (no static work) with S free node and var slots in every
cell plus a 16-slot region per cell outside the free stacks (cell (0,0): the controller's root-var pool; elsewhere
unused, so every cell starts with exactly S free slots, as in the fabric model), writes the job table (owner, typed,
reservation (W_nodes, B_vars) or (B_nodes, B_vars), REF of the job's @main) and the budget S - margin computed
exactly as omega/admission.Scheduler does, and runs the mesh with +adm=1.  The controller's event lines (start /
reject / done / viol / end) come back parsed.

`run_static(jobs, W, H, S)` is the no-admission counterpart: every job loaded at cycle 0 exactly as
admission.Scheduler(admit=False) loads it (the step-24 multi-tenant behaviour), run with +adm=0.
"""
import os
from . import fabric, ir, rtl, admission
from .ports import *

RR = 16          # root-var pool of the controller (rtl/omega_adm.sv RR)
NJ = 512         # job table size (rtl/omega_adm.sv NJ)


class AdmImage(fabric.Image):
    adm = True

    def write_hex(self, outdir):
        super().write_hex(outdir)
        h = lambda v: format(v, "016x")
        with open(f"{outdir}/adm_cfg.hex", "w") as f:
            f.write("".join(format(v, "08x") + "\n" for v in self.adm_cfg + [0] * (8 - len(self.adm_cfg))))
        with open(f"{outdir}/adm_info.hex", "w") as f:
            f.write("".join(h(v) + "\n" for v in self.adm_info))
        with open(f"{outdir}/adm_ref.hex", "w") as f:
            f.write("".join(h(v) + "\n" for v in self.adm_ref))


def budget_of(book, W, H, S):
    dmax = max(max(len(d.nodes), d.nvars) for d in book.defs)
    margin = 0 if W * H == 1 else dmax + max(fabric.LM_RSV, fabric.RSV)
    return margin, (S - margin, S - margin)


def run_admitted(jobs, W, H, S, seed=1, mut=0, maxcycles=20_000_000, timeout=3000, noprog=0, keep=None, placement=False):
    """placement=True (step 29, SPEC 7.8): budgets from the placement certificate (admission.placement_budget,
    margin 0) instead of S - margin; the controller is unchanged (only its configuration words differ)."""
    if len(jobs) > NJ: raise ValueError("job table holds 512 jobs")
    book = admission.merge_unique(jobs)
    margin, budget = budget_of(book, W, H, S)
    if placement and W * H > 1: margin, budget = admission.placement_budget(jobs, W, H, S)
    P = S + RR
    img = AdmImage(book, W, H, P, 1024, tenants=[{"owner": 0, "main": jobs[0].main}])
    for c in img.nodes:                                   # empty image; the region [S, S + RR) is outside the free stacks
        img.nodes[c] = [None] * S + [[0, 0]] * RR; img.nown[c] = [OWNER_FREE] * P
        img.vars[c] = [None] * S + [mk(NONE)] * RR; img.vown[c] = [OWNER_FREE] * P
        img.queue[c] = []
    img.tenants, img.roots = [], []
    img.root = mk(VAR, 0, addr(0, 0, S))
    img.adm_cfg = [len(jobs), budget[0], budget[1], S, margin, W * H * S]
    img.adm_info = [((j.need[1] if j.typed else 0) << 40) | ((j.need[0] if j.typed else 0) << 16) | (int(j.typed) << 4) | j.owner
                    for j in jobs]
    img.adm_ref = [mk(REF, j.main, 0, owner=j.owner) for j in jobs]
    r = rtl.run(book, W, H, seed=seed, slots=P, img=img, mut=mut, maxcycles=maxcycles, timeout=timeout,
                extra=["+adm=1", f"+noprog={noprog}"], want_dump=True, keep=keep)
    ev = r.get("adm_log", [])
    st = {k: {"state": "queued", "start": None, "end": None, "slot": None, "word": None} for k in range(len(jobs))}
    end = None
    for e in ev:
        if e[0] == "start": st[e[1]].update(state="running", start=e[2], slot=e[3])
        elif e[0] == "reject": st[e[1]].update(state="rejected")
        elif e[0] == "done": st[e[1]].update(state="done", end=e[2], word=e[4])
        elif e[0] == "end": end = e
    for k, j in enumerate(jobs):
        s = st[k]
        if s["word"] is None: s["result"] = None
        elif tag(s["word"]) in (NUM, ERA):
            s["result"] = fabric.readback_dump(book, {}, {(0, 0): [s["word"]]}, mk(VAR, 0, addr(0, 0, 0)))
        else:                                             # a data result stays in the fabric: read it from the dump
            try:
                s["result"] = fabric.readback_dump(book, r["_nodes"], r["_vars"], mk(VAR, 0, addr(0, 0, S + s["slot"]), owner=j.owner))
            except Exception as e:
                s["result"] = f"ERROR {type(e).__name__}"
    out = {"status": r["status"], "cycles": r.get("cycles"), "interactions": r.get("interactions"), "budget": budget,
           "margin": margin, "events": ev, "blocked": any(e[0] == "blocked" for e in ev),
           "viol": [e for e in ev if e[0] == "viol"],
           "jobs": [dict(name=j.name, owner=j.owner, typed=j.typed, need=j.need, **st[k]) for k, j in enumerate(jobs)]}
    if end:
        out.update(peak_live=(end[2], end[3]), max_reserved=(end[4], end[5]), nviol=end[6], adm_err=end[7])
    return out


def run_static(jobs, W, H, S, seed=1, maxcycles=5_000_000, noprog=20000, timeout=3000):
    """Every job loaded at cycle 0 (admission.Scheduler(admit=False).load), then the plain mesh (+adm=0)."""
    sch = admission.Scheduler(jobs, W, H, S, admit=False, dedupe=True)
    for j in list(sch.queue): sch.queue.remove(j); sch.load(j)
    img = fabric.Image(sch.book, W, H, S, 1024, tenants=[{"owner": 0, "main": jobs[0].main}])
    for xy, c in sch.fab.cells.items():
        img.nodes[xy] = [None if e is None else list(e) for e in c.nodes]
        img.vars[xy] = list(c.vars); img.nown[xy] = list(c.nown); img.vown[xy] = list(c.vown)
        img.queue[xy] = list(c.queue)
    img.tenants = [{"owner": j.owner, "main": j.main} for j in jobs]
    img.roots = [j.root for j in jobs]
    img.root = jobs[0].root
    r = rtl.run(sch.book, W, H, seed=seed, slots=S, img=img, maxcycles=maxcycles, timeout=timeout, extra=[f"+noprog={noprog}"])
    return {"status": r["status"], "cycles": r.get("cycles"), "interactions": r.get("interactions"),
            "results": [t["readback"] for t in r["tenants"]]}
