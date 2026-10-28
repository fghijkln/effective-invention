"""Standard-cell flow for one TACHYON-Omega cell, the cluster ROM, and the TACHYON-128 core (step 8).

OpenROAD is not available for this host (linux-aarch64: no conda / litex-hub package; a source build
of OpenROAD and its dependencies is out of scope), so the flow stops before place and route:

  1. Yosys 0.70 (yowasp)   generic synthesis as in synth_cell.ys, memories kept as $mem_v2 macros;
                            every memory becomes a black-box macro cell M_<module>_<k>
  2. Yosys                 dfflibmap + abc -D <period> onto the Nangate45 (FreePDK45) Open Cell
                            Library, typical corner (1.1 V, 25 C); `stat -liberty` = standard-cell area
  3. mems.lib (generated)  a Liberty model per memory macro: area = bits x the average density of the
                            OpenROAD fakeram45 macros (1024x32, 2048x39, 512x64) x a port factor
                            (1 + 0.5 per port beyond one), timing = fakeram45 numbers (clock-to-out
                            0.309 ns, setup/hold 0.050 ns; asynchronous read ports: 0.309 ns address-to-data)
  3b. buffer_nets.py       fanout repair (buffer trees on nets with > 16 sinks), a stand-in for
                            OpenROAD repair_design; inserted buffers are added to the area
  4. OpenSTA 3.1 (built from source)  pre-layout STA (inputs 0.1 ns after the clock, outputs 0.05 ns
                            before it: the mesh neighbours are registered) with the library's default wire-load model
                            (5K_hvratio_1_1); Fmax = 1 / (period - worst slack)

usage: python3 synth/flow.py {omega_cell|omega_rom|tx_core|all} [--period NS] [--cpu128 DIR]
Outputs: synth/out/<design>/{stat.txt, net.v (not committed), mems.lib, sta.txt, summary.json}
"""
import json, os, re, subprocess, sys, urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PDK = os.path.join(ROOT, "synth", "pdk")
ORFS = "https://raw.githubusercontent.com/The-OpenROAD-Project/OpenROAD-flow-scripts/master/flow/platforms/nangate45/"
LIB = os.path.join(PDK, "NangateOpenCellLibrary_typical.lib")
FAKERAM = ["1024x32", "2048x39", "512x64"]
YOSYS = os.environ.get("YOSYS", os.path.expanduser("~/.local/bin/yowasp-yosys"))
STA = os.environ.get("STA", os.path.expanduser("~/bin/sta"))
CPU128 = os.environ.get("CPU128", "/workspace/work/cpu128")

DESIGNS = {
    "omega_cell": dict(top="omega_cell", inc=["rtl"], files=["rtl/omega_router.sv", "rtl/omega_cell.sv"],
                       params="-set X 1 -set Y 1 -set W 4 -set H 4 -set SLOTS 1024 -set QDEPTH 1024 -set DIRSZ 256",
                       clk="clk"),
    "omega_rom": dict(top="omega_rom", inc=["rtl"], files=["rtl/omega_rom.sv"],
                      params="-set NC 4 -set NP 1 -set ROMSZ 4096 -set RDXSZ 2048", clk="clk"),
    "omega_rom_4x4p2": dict(top="omega_rom", inc=["rtl"], files=["rtl/omega_rom.sv"],
                            params="-set NC 16 -set NP 2 -set ROMSZ 4096 -set RDXSZ 2048", clk="clk"),
    "tx_core": dict(top="tx_core", inc=["@/rtl"], files=["@/rtl/tx_alu.sv", "@/rtl/tx_simd.sv", "@/rtl/tx_mul32x4.sv",
                                                         "@/rtl/tx_muldiv.sv", "@/rtl/tx_core.sv"], params="", clk="clk"),
}


def fetch_pdk():
    os.makedirs(PDK, exist_ok=True)
    want = [("lib/NangateOpenCellLibrary_typical.lib", LIB)]
    for n in FAKERAM:
        want.append((f"lef/fakeram45_{n}.lef", os.path.join(PDK, f"fakeram45_{n}.lef")))
    for url, path in want:
        if not os.path.exists(path):
            urllib.request.urlretrieve(ORFS + url, path)


def sram_density():
    """um^2 per bit, from the fakeram45 macro footprints (LEF SIZE)."""
    d = []
    for n in FAKERAM:
        txt = open(os.path.join(PDK, f"fakeram45_{n}.lef")).read()
        w, h = map(float, re.search(r"SIZE\s+([\d.]+)\s+BY\s+([\d.]+)", txt).groups())
        words, bits = map(int, n.split("x"))
        d.append(w * h / (words * bits))
    return sum(d) / len(d), d


def path(p):
    return p.replace("@", CPU128) if p.startswith("@") else os.path.join(ROOT, p)


def yosys(script, log):
    with open(log, "w") as f:
        r = subprocess.run([YOSYS, "-q", "-s", script], cwd=ROOT, stdout=f, stderr=subprocess.STDOUT)
    if r.returncode:
        raise RuntimeError(f"yosys failed, see {log}")


def parse_mems(il):
    """$mem_v2 cells (renamed omem_<k>) per module of an RTLIL file -> list of dicts."""
    mems, mod, cur = [], None, None
    for line in open(il):
        t = line.split()
        if not t: continue
        if t[0] == "module": mod = t[1]
        elif t[0] == "cell" and t[1] == "$mem_v2": cur = dict(module=mod, name=t[2], p={})
        elif t[0] == "parameter" and cur is not None and len(t) >= 3:
            v = t[2]
            if re.fullmatch(r"-?\d+", v): cur["p"][t[1].lstrip("\\")] = int(v)
            elif re.fullmatch(r"\d+'[01xz]+", v): cur["p"][t[1].lstrip("\\")] = v.split("'")[1]
            elif t[1] == "\\MEMID": cur["p"]["MEMID"] = " ".join(t[2:]).strip('"').lstrip("\\")
        elif t[0] == "end" and cur is not None:
            mems.append(cur); cur = None
    return mems


def bus(name, w, direction, extra=""):
    if w == 1:
        return f"    pin({name}) {{ direction : {direction}; {extra} }}\n"
    return (f"    bus({name}) {{ bus_type : b{w}; direction : {direction}; {extra} }}\n")


def mem_lib(mems, density):
    """Liberty cells for the memory macros (timing numbers from fakeram45_1024x32.lib)."""
    widths = set()
    cells = []
    for m in mems:
        p = m["p"]
        A, Wd, R, Wp = p["ABITS"], p["WIDTH"], p["RD_PORTS"], p["WR_PORTS"]
        bits = p["SIZE"] * Wd
        ports = R + Wp
        area = bits * density * (1 + 0.5 * (ports - 1))
        m.update(bits=bits, area=area, ports=ports,
                 cell="M_" + re.sub(r"\W", "_", m["module"].lstrip("\\")) + "_" + re.sub(r"\W", "_", m["name"].lstrip("\\")))
        rce = p.get("RD_CLK_ENABLE", "1" * R)
        rce = rce if isinstance(rce, str) else format(rce, f"0{R}b")
        sync = "1" in rce
        pins = dict(RD_CLK=R, RD_EN=R, RD_ARST=R, RD_SRST=R, RD_ADDR=R * A, RD_DATA=R * Wd,
                    WR_CLK=Wp, WR_EN=Wp * Wd, WR_ADDR=Wp * A, WR_DATA=Wp * Wd)
        s = f"  cell({m['cell']}) {{\n    area : {area:.1f};\n    dont_touch : true;\n    dont_use : true;\n"
        for n, w in pins.items():
            if w == 0: continue
            widths.add(w)
            if n in ("RD_CLK", "WR_CLK"):
                s += bus(n, w, "input", "capacitance : 25.0; clock : true;")
            elif n == "RD_DATA":
                if sync:
                    tm = ('timing() { related_pin : "RD_CLK"; timing_type : rising_edge; '
                          'cell_rise(scalar) { values("0.309"); } cell_fall(scalar) { values("0.309"); } '
                          'rise_transition(scalar) { values("0.050"); } fall_transition(scalar) { values("0.050"); } }')
                else:
                    tm = ('timing() { related_pin : "RD_ADDR"; timing_sense : non_unate; '
                          'cell_rise(scalar) { values("0.309"); } cell_fall(scalar) { values("0.309"); } '
                          'rise_transition(scalar) { values("0.050"); } fall_transition(scalar) { values("0.050"); } }')
                s += bus(n, w, "output", "max_capacitance : 500.0; " + tm)
            else:
                clkpin = "WR_CLK" if n.startswith("WR") else "RD_CLK"
                tm = ""
                if (n.startswith("WR") and Wp) or (n.startswith("RD") and sync and n != "RD_ARST"):
                    tm = (f'timing() {{ related_pin : "{clkpin}"; timing_type : setup_rising; '
                          'rise_constraint(scalar) { values("0.050"); } fall_constraint(scalar) { values("0.050"); } } '
                          f'timing() {{ related_pin : "{clkpin}"; timing_type : hold_rising; '
                          'rise_constraint(scalar) { values("0.050"); } fall_constraint(scalar) { values("0.050"); } }')
                s += bus(n, w, "input", "capacitance : 5.0; " + tm)
        s += "  }\n"
        cells.append(s)
    hdr = ("library(omega_mems) {\n  delay_model : table_lookup;\n  time_unit : \"1ns\";\n  voltage_unit : \"1V\";\n"
           "  current_unit : \"1mA\";\n  capacitive_load_unit (1,ff);\n  pulling_resistance_unit : \"1kohm\";\n"
           "  leakage_power_unit : \"1nW\";\n  nom_process : 1.0; nom_voltage : 1.1; nom_temperature : 25.0;\n"
           "  default_max_transition : 0.227;\n  input_threshold_pct_rise : 50; input_threshold_pct_fall : 50;\n"
           "  output_threshold_pct_rise : 50; output_threshold_pct_fall : 50;\n  slew_lower_threshold_pct_rise : 20;\n"
           "  slew_lower_threshold_pct_fall : 20; slew_upper_threshold_pct_rise : 80; slew_upper_threshold_pct_fall : 80;\n"
           "  slew_derate_from_library : 1.0;\n")
    for w in sorted(widths):
        hdr += (f"  type(b{w}) {{ base_type : array; data_type : bit; bit_width : {w}; bit_from : {w - 1}; "
                f"bit_to : 0; downto : true; }}\n")
    return hdr + "".join(cells) + "}\n"


def run(design, period):
    fetch_pdk()
    dens, dens_all = sram_density()
    d = DESIGNS[design]
    out = os.path.join(ROOT, "synth", "out", design)
    os.makedirs(out, exist_ok=True)
    rd = (f"read_verilog -sv -DSYNTHESIS " + " ".join("-I" + path(i) for i in d["inc"]) + " "
          + " ".join(path(f) for f in d["files"]) + "\n")
    if d["params"]:
        rd += f"chparam {d['params']} {d['top']}\n"
    pre = os.path.join(out, "pre.il")
    s1 = os.path.join(out, "pass1.ys")
    open(s1, "w").write(rd + f"""hierarchy -check -top {d['top']}
proc
opt_expr
opt_clean
opt -nodffe -nosdff
memory -nomap
opt -full
wreduce
peepopt
alumacc
share
opt
memory -nomap
opt -fast
rename -enumerate -pattern omem_% t:$mem_v2
write_rtlil {pre}
""")
    net = os.path.join(out, "net.v")
    post = os.environ.get("OMEGA_SYNTH_POST") == "1" and os.path.exists(net)   # reuse net.v: fanout repair + STA only
    if not post: yosys(s1, os.path.join(out, "pass1.log"))
    mems = parse_mems(pre)
    lib = mem_lib(mems, dens)
    mlib = os.path.join(out, "mems.lib")
    open(mlib, "w").write(lib)
    s2 = os.path.join(out, "pass2.ys")
    ch = ""
    for m in mems:
        sel = m['module'].lstrip('\\') + "/" + m['name'].lstrip('\\')
        ch += f"chtype -set {m['cell']} {sel}\n"
        for k in list(m["p"]) + ["INIT", "OFFSET", "RD_CLK_POLARITY", "RD_TRANSPARENCY_MASK", "RD_COLLISION_X_MASK",
                                 "RD_WIDE_CONTINUATION", "RD_CE_OVER_SRST", "RD_ARST_VALUE", "RD_SRST_VALUE",
                                 "RD_INIT_VALUE", "WR_CLK_ENABLE", "WR_CLK_POLARITY", "WR_PRIORITY_MASK",
                                 "WR_WIDE_CONTINUATION"]:
            ch += f"setparam -unset {k} {sel}\n"
    net = os.path.join(out, "net.v")
    open(s2, "w").write(f"""read_rtlil {pre}
{ch}techmap
opt -fast
dfflibmap -liberty {LIB}
abc -liberty {LIB} -D {int(period * 1000)}
opt_clean
hilomap -singleton -hicell LOGIC1_X1 Z -locell LOGIC0_X1 Z
setundef -zero
opt_clean
tee -o {out}/stat.txt stat -liberty {LIB} -liberty {mlib} -top {d['top']}
tee -o {out}/stat_std.txt stat -liberty {LIB} -top {d['top']}
write_verilog -noattr -noexpr -nohex -nodec {net}
""")
    if not post: yosys(s2, os.path.join(out, "pass2.log"))
    # fanout repair (stand-in for OpenROAD repair_design): buffer trees on nets with > 16 sinks
    netb = os.path.join(out, "net_buf.v")
    rb = subprocess.run([sys.executable, os.path.join(ROOT, "synth", "buffer_nets.py"), net, netb, LIB, mlib],
                        capture_output=True, text=True)
    if rb.returncode:
        raise RuntimeError("buffer_nets failed: " + rb.stderr[-2000:])
    nb = {k: 0 for k in ("BUF_X4", "BUF_X8")}
    for line in open(netb):
        t = line.split()
        if t and t[0] in nb and t[1].startswith("_fb"): nb[t[0]] += 1
    libtxt = open(LIB).read()
    barea = sum(n * float(re.search(r"cell \(%s\)\s*\{.*?area\s*:\s*([\d.]+)" % c, libtxt, re.S).group(1)) for c, n in nb.items())
    sta = os.path.join(out, "sta.tcl")
    clk = d["clk"]
    open(sta, "w").write(f"""read_liberty {LIB}
read_liberty {mlib}
read_verilog {netb}
link_design {d['top']}
set_wire_load_model -name 5K_hvratio_1_1
create_clock -name clk -period {period} [get_ports {clk}]
set_input_delay 0.1 -clock clk [delete_from_list [all_inputs] [get_ports {clk}]]
set_output_delay 0.05 -clock clk [all_outputs]
puts "WORST_SLACK [sta::worst_slack_cmd max]"
report_checks -path_delay max -digits 3 -group_path_count 1
puts "REG2REG"
report_checks -path_delay max -from [all_registers -clock_pins] -to [all_registers -data_pins] -digits 3
puts "REG2REG_SLACK [sta::format_time [sta::worst_slack_cmd max] 3]"
exit
""")
    r = subprocess.run([STA, "-no_splash", "-exit", sta], capture_output=True, text=True, cwd=out)
    open(os.path.join(out, "sta.txt"), "w").write(r.stdout + r.stderr)
    m = re.search(r"WORST_SLACK (\S+)", r.stdout)
    slack = float(m.group(1)) * (1e9 if abs(float(m.group(1))) < 1e-3 else 1) if m else None
    # reg-to-reg worst path: parse its slack line
    rr = None
    if "REG2REG" in r.stdout:
        tail = r.stdout.split("REG2REG", 1)[1]
        mm = re.search(r"(-?[\d.]+)\s+slack", tail)
        rr = float(mm.group(1)) if mm else None
    st = open(os.path.join(out, "stat.txt")).read()
    std = open(os.path.join(out, "stat_std.txt")).read()
    area = float(re.findall(r"Chip area for (?:top )?module.*?:\s*([\d.]+)", st)[-1])
    area_std = float(re.findall(r"Chip area for (?:top )?module.*?:\s*([\d.]+)", std)[-1])
    mem_area = sum(m["area"] for m in mems)
    cells = re.findall(r"^\s+(\d+)\s+cells\s*$", std, re.M)
    summ = dict(design=design, period_ns=period, std_cell_area_um2=area_std + barea, buffer_area_um2=barea,
                buffers=nb, mem_area_um2=mem_area,
                total_area_um2=area_std + barea + mem_area, stat_total_area_um2=area,
                mem_bits=sum(m["bits"] for m in mems), sram_density_um2_per_bit=dens, fakeram_densities=dens_all,
                worst_slack_ns=slack, fmax_mhz=(1000.0 / (period - slack)) if slack is not None else None,
                reg2reg_slack_ns=rr, fmax_reg2reg_mhz=(1000.0 / (period - rr)) if rr is not None else None,
                mems=[dict(module=m["module"], memid=m["p"].get("MEMID", "?"), words=m["p"]["SIZE"], width=m["p"]["WIDTH"],
                           rd_ports=m["p"]["RD_PORTS"], wr_ports=m["p"]["WR_PORTS"], bits=m["bits"], area_um2=round(m["area"], 1))
                      for m in mems])
    json.dump(summ, open(os.path.join(out, "summary.json"), "w"), indent=1)
    print(json.dumps({k: v for k, v in summ.items() if k != "mems"}), flush=True)
    return summ


if __name__ == "__main__":
    period = float(sys.argv[sys.argv.index("--period") + 1]) if "--period" in sys.argv else 2.0
    if "--cpu128" in sys.argv:
        CPU128 = sys.argv[sys.argv.index("--cpu128") + 1]
    which = sys.argv[1]
    for dsg in (["omega_rom", "omega_cell", "tx_core"] if which == "all" else [which]):
        run(dsg, period)
