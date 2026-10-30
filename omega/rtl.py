"""Verilator harness for the RTL mesh: build per configuration, write the memory image, run,
read the node/var RAM dumps back and read back the normal form."""
import os, subprocess, tempfile, shutil, hashlib
from .ports import *
from . import fabric

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RTL = ["rtl/omega_router.sv", "rtl/omega_rom.sv", "rtl/omega_cell.sv", "rtl/omega_mesh.sv"]
HDRS = ["rtl/omega_defs.svh", "rtl/omega_funcs.svh"]
RDXSZ = 2048
BUILD = os.environ.get("OMEGA_BUILD", "/tmp/omega_build")
ENV_SH = os.environ.get("OMEGA_ENV_SH", os.path.expanduser("~/env.sh"))


def _env():
    env = dict(os.environ)
    if os.path.exists(ENV_SH):
        out = subprocess.run(["bash", "-c", f"source {ENV_SH} && env"], capture_output=True, text=True).stdout
        for line in out.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                env[k] = v
    return env


_ENV = None


# cluster ROM configuration (step 7): CW x CH cells share one ROM with RPORTS read ports.
# Default from the environment (OMEGA_CLUSTER="2x2:1"), else 2x2 with one port.
def _cluster_default():
    v = os.environ.get("OMEGA_CLUSTER", "2x2:1")
    shape, _, ports = v.partition(":")
    cw, ch = (int(t) for t in shape.split("x"))
    return cw, ch, int(ports or 1)


CLUSTER = _cluster_default()


def build(W, H, slots=1024, qdepth=1024, romsz=4096, mut=0, quiet=True, cluster=None):
    global _ENV
    if _ENV is None:
        _ENV = _env()
    src_hash = hashlib.sha1(b"".join(open(os.path.join(ROOT, f), "rb").read() for f in RTL + ["tb/tb_mesh.cpp"])).hexdigest()[:10]
    cw, ch, rp = cluster or CLUSTER
    name = f"v{W}x{H}_s{slots}_q{qdepth}_r{romsz}_m{mut:x}_c{cw}x{ch}p{rp}_{src_hash}"
    d = os.path.join(BUILD, name)
    exe = os.path.join(d, "vsim")
    if os.path.exists(exe):
        return exe
    os.makedirs(BUILD, exist_ok=True)
    cmd = ["verilator", "--cc", "--exe", "--build", "-j", os.environ.get("OMEGA_JOBS", "2" if W * H < 64 else "1"), "-O3", "-Wno-fatal", "-Wno-WIDTH", "-Wno-UNUSED",
           "-Wno-MULTIDRIVEN", "-Irtl", "--top-module", "omega_mesh", f"-GW={W}", f"-GH={H}", f"-GSLOTS={slots}",
           f"-GQDEPTH={qdepth}", f"-GROMSZ={romsz}", f"-GRDXSZ={RDXSZ}", f"-GCW={cw}", f"-GCH={ch}", f"-GRPORTS={rp}", f"-GMUT=256'h{mut:x}", "-Mdir", d, "-o", "vsim",
           "-CFLAGS", "-O1"] + (["--output-split", os.environ.get("OMEGA_SPLIT", "1500"), "--output-split-cfuncs", os.environ.get("OMEGA_SPLIT", "1500"), "--output-groups", "0"] if W * H >= 32 else []) + [os.path.join(ROOT, f) for f in RTL + ["tb/tb_mesh.cpp"]]
    r = subprocess.run(cmd, cwd=ROOT, env=_ENV, capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(exe):
        raise RuntimeError("verilator build failed:\n" + r.stdout[-3000:] + r.stderr[-3000:])
    # keep only the binary (object files are large)
    for f in os.listdir(d):
        if f != "vsim":
            p = os.path.join(d, f)
            if os.path.isfile(p): os.remove(p)
    return exe


def _readhex(path, n):
    out = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("//"): continue
            out.append(int(line, 16))
    return out[:n] if n else out


def run(book, W, H, seed=1, jitter=0, stall=0, pmsg=128, slots=1024, qdepth=1024, romsz=4096,
        mut=0, maxcycles=20_000_000, keep=None, img=None, timeout=600, fi=0, cluster=None, spawn=None, link_local=None, s14=None, govnb=None, govl0=None):
    """spawn = (K, hint[, K2[, KP[, GOV]]]): step-11/13 spawn policy (default: fabric.SPAWN_K / SPAWN_HINT /
    SPAWN_K2 / SPAWN_KP / GOV_B, env OMEGA_SPAWN_K ...); K = -1 hands every REF to a hungry neighbour (the
    step-10 policy); KP = producer-recursion threshold, GOV = message budget (0 = governor off)."""
    dflt = (fabric.SPAWN_K, fabric.SPAWN_HINT, fabric.SPAWN_K2, fabric.SPAWN_KP, fabric.GOV_B)
    sk, sh, sk2, skp, gov = (tuple(spawn) + dflt[len(spawn):])[:5] if spawn else dflt
    ll = fabric.LINK_LOCAL if link_local is None else link_local     # step 12 (OMEGA_LINK_LOCAL)
    s14 = fabric.S14 if s14 is None else int(s14)                     # step 14 fork deque mode (OMEGA_S14)
    govnb = (fabric.S14_GOVNB if s14 else 0) if govnb is None else govnb
    govl0 = (fabric.S14_GOVL0 if s14 else 2) if govl0 is None else govl0
    exe = build(W, H, slots, qdepth, romsz, mut, cluster=cluster)
    img = img or fabric.Image(book, W, H, slots, qdepth)
    if len(img.romn) > romsz or len(img.romr) > RDXSZ or len(img.dir) > 256:
        raise fabric.FabricError("book does not fit the ROM")
    tmp = keep or tempfile.mkdtemp(prefix="omg_")
    try:
        img.write_hex(tmp)
        r = subprocess.run([exe, f"+img={tmp}", f"+seed={seed}", f"+jitter={jitter}", f"+stall={stall}",
                            f"+pmsg={pmsg}", f"+maxcycles={maxcycles}", f"+fi={fi}",
                            f"+spawnk={255 if sk < 0 else min(sk, 254)}", f"+spawnhint={int(bool(sh))}", f"+linklocal={int(bool(ll))}",
                            f"+spawnk2={255 if sk2 < 0 else min(sk2, 254)}", f"+spawnkp={255 if skp < 0 else min(skp, 254)}",
                            f"+govb={max(0, min(gov, 255))}", f"+s14={s14}", f"+govnb={govnb}", f"+govl0={govl0}", f"+rto={fabric.RTO}", f"+rgrad={fabric.RGRAD}", f"+rsv={fabric.RSV}"], capture_output=True, text=True, timeout=timeout)
        res = {}
        for line in r.stdout.splitlines():
            k, _, v = line.partition(" ")
            if v.strip().lstrip("-").isdigit(): res[k] = int(v)
        if "status" not in res:
            raise RuntimeError("simulator crashed: " + r.stdout[-2000:] + r.stderr[-2000:])
        nodes, vars_, cells, nown = {}, {}, {}, {}
        for x in range(W):
            for y in range(H):
                nm = _readhex(f"{tmp}/out_node_{x}_{y}.hex", slots)
                na = _readhex(f"{tmp}/out_nalloc_{x}_{y}.hex", slots)
                vm = _readhex(f"{tmp}/out_var_{x}_{y}.hex", slots)
                # v2 dump: node word {owner, aux2, aux1}, var word {owner, port}
                nodes[(x, y)] = [[w & M64, (w >> 64) & M64] if a else None for w, a in zip(nm, na)]
                vars_[(x, y)] = [w & M64 for w in vm]
                nown[(x, y)] = [w >> 128 for w in nm]
                st = {}
                with open(f"{tmp}/out_stats_{x}_{y}.txt") as f:
                    for line in f:
                        k, v = line.split()
                        st[k] = int(v)
                cells[(x, y)] = st
        res["cells"] = cells
        res["node_count"] = sum(sum(e is not None for e in t) for t in nodes.values())
        if res["status"] == 0:
            try:
                res["readback"] = fabric.readback_dump(book, nodes, vars_, img.root)
            except Exception as e:
                res["readback"] = f"ERROR {e}"
        else:
            res["readback"] = f"STATUS {res['status']} err {res.get('err')}"
        # owner capabilities: per-tenant results and the (reason, owner) trap set
        res["tenants"] = []
        for k, t in enumerate(img.tenants):
            if res["status"] == 0:
                try:
                    rb = fabric.readback_dump(book, nodes, vars_, img.roots[k])
                except Exception as e:
                    rb = f"ERROR {type(e).__name__}"
            else:
                rb = res["readback"]
            res["tenants"].append({"owner": t["owner"], "readback": rb,
                                   "nodes": sum(1 for c in nodes for s, e in enumerate(nodes[c])
                                                if e is not None and nown[c][s] == t["owner"])})
        res["traps"] = sorted({(b // 16 + 1, b % 16) for c in cells.values() for b in range(48) if c.get("trap_mask", 0) >> b & 1})
        res["trap_count"] = sum(c.get("traps", 0) for c in cells.values())
        res["trap_first"] = {k: (c["trap_reason"], c["trap_owner"], c["trap_addr"]) for k, c in cells.items() if c.get("traps")}
        res["fgive"] = sum(c.get("fgive", 0) for c in cells.values())
        res["msgs"] = {k: sum(c[k] for c in cells.values()) for k in ("msg_link", "msg_node", "msg_spawn")}
        busy = [c["busy"] for c in cells.values()]
        res["util"] = sum(busy) / (len(busy) * max(1, res.get("cycles", 1)))
        return res
    finally:
        if not keep:
            shutil.rmtree(tmp, ignore_errors=True)
