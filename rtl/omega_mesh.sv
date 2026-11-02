// TACHYON-Omega W x H mesh of active memory cells.  The only global wires are clock, reset,
// the verification knobs (seed / jitter / stall), the quiescence AND-tree (termination detection,
// SPEC 8) and the dump strobe used by the testbench to read the node RAMs back.
`include "omega_defs.svh"
module omega_mesh #(
  parameter int W = 2, parameter int H = 2, parameter int SLOTS = 1024, parameter int QDEPTH = 1024,
  parameter int ROMSZ = 4096, parameter int DIRSZ = 256, parameter int DEPTH = 4, parameter int RDXSZ = 2048,
  parameter int CW = 1, parameter int CH = 1,      // cluster of CW x CH cells shares one definition ROM
  parameter int RPORTS = 1,                        // read ports of the cluster ROM
  parameter logic [511:0] MUT = '0
) (
  input  logic        clk, rst,
  input  logic [31:0] seed,
  input  logic [7:0]  jitter, stall, pmsg,
  input  logic [7:0]  fi,
  input  logic [7:0]  spawn_k,             // step 11 spawn policy (configuration, SPEC 5)
  input  logic        spawn_hint,
  input  logic [7:0]  spawn_k2,
  input  logic [7:0]  spawn_kp,            // step 13 producer threshold / message-budget governor (SPEC 5.2)
  input  logic [7:0]  gov_b,
  input  logic [1:0]  fork_dq,             // step 14 fork deque + oldest-fork give (SPEC 5.3; 0 = step 13)
  input  logic [3:0]  gov_nb,              // step 14 governor: relax with a hungry neighbour (0 = off)
  input  logic [2:0]  gov_l0,              //   governor reset level
  input  logic [5:0]  rto_m1,              //   step 18: retry-slot timeout - 1
  input  logic [2:0]  rgrad,               //   step 19: room-distance gradient cap (0 = off)
  input  logic [2:0]  rsv,                 //   step 20: reserve with room downhill (step 19: 4)
  input  logic [1:0]  lm_mode,             //   step 22: low-memory mode (0 = off, 1 = while no cell is ample, 2 = always)
  input  logic [7:0]  lm_hi,               //     low-memory roomy watermarks (set / clear)
  input  logic [7:0]  lm_lo,
  input  logic [4:0]  lm_rsv,              //     reserve with room downhill in low-memory mode
  input  logic [1:0]  ilr,                 //   step 23: 1 = internal redexes before an expansion's root link, 2 = also fabric child order (0 = step 22)
  input  logic        adm_on,              // step 26: admission controller (0 = off = step 25)
  input  logic        link_local,          // step 12 local-first link orientation (configuration, SPEC 4)
  input  logic        dump,
  output logic        all_ready,
  output logic        all_idle,
  output logic [3:0]  any_err,
  output logic [31:0] interactions
);
  // per-cell link wires, indexed [x][y][dir]  (dir 0 N, 1 E, 2 S, 3 W)
  logic [3:0]  ov   [W][H];
  flit_t [3:0] of   [W][H];
  logic [3:0]  ordy [W][H];
  logic [3:0]  iv   [W][H];
  flit_t [3:0] inf  [W][H];
  logic [3:0]  irdy [W][H];
  logic  cidle [W][H];
  logic  chung [W][H];
  logic [3:0]  nhung [W][H];
  logic        croom [W][H];
  logic [3:0]  nroom [W][H];
  logic [2:0]  crd [W][H];                 // step 19 room distance
  logic [3:0][2:0] nrd [W][H];
  logic  crdy [W][H];
  logic [3:0]  cerr [W][H];
  logic [31:0] cint [W][H];
  logic        rreq [W][H];
  logic [15:0] ran  [W][H];
  logic [15:0] rar  [W][H];
  logic        rgnt [W][H];
  logic [511:0] rdn [W][H];
  logic [511:0] rdr [W][H];
  // step 26 admission controller wiring (host port of cell (0,0))
  logic        c_hq_ack [W][H], c_hw_ack [W][H], c_mwe [W][H], c_mwe2 [W][H];
  logic [15:0] c_mwa [W][H], c_mwa2 [W][H];
  logic [63:0] c_mwd [W][H], c_mwd2 [W][H];
  logic [16:0] c_fn [W][H], c_fv [W][H];
  logic [31:0] c_tq [W][H];               // step 30: task entries per cell (audit only)
  logic        a_hq_v, a_hw_v, adm_idle, cells_idle;
  logic [63:0] a_hq_a, a_hq_b;
  logic [15:0] a_hw_a, a_rb;
  logic [67:0] a_hw_d;
  logic [3:0]  adm_err;
  logic [31:0] sum_fn, sum_fv, min_f;

  // ---- cluster ROMs: cell (x, y) is member (x % CW) + (y % CH) * CW of cluster (x / CW, y / CH) ----
  localparam int NCX = (W + CW - 1) / CW, NCY = (H + CH - 1) / CH;
  for (genvar cx = 0; cx < NCX; cx++) begin : gcx
    for (genvar cy = 0; cy < NCY; cy++) begin : gcy
      logic [CW*CH-1:0] req, gnt;
      logic [CW*CH-1:0][15:0] an, ar;
      logic [CW*CH-1:0][511:0] dn, dr;
      for (genvar k = 0; k < CW * CH; k++) begin : gk
        localparam int XX = cx * CW + k % CW, YY = cy * CH + k / CW;
        if (XX < W && YY < H) begin : gin
          assign req[k] = rreq[XX][YY]; assign an[k] = ran[XX][YY]; assign ar[k] = rar[XX][YY];
          assign rgnt[XX][YY] = gnt[k]; assign rdn[XX][YY] = dn[k]; assign rdr[XX][YY] = dr[k];
        end else begin : gout
          assign req[k] = 1'b0; assign an[k] = '0; assign ar[k] = '0;
        end
      end
      omega_rom #(.NC(CW * CH), .NP(RPORTS), .ROMSZ(ROMSZ), .RDXSZ(RDXSZ), .CX(cx), .CY(cy), .MUT(MUT)) u_rom (
        .clk, .rst, .req, .an, .ar, .gnt, .dn, .dr,
        .cfg_we(1'b0), .cfg_sel(2'd0), .cfg_a(16'd0), .cfg_d(512'd0));
    end
  end

  for (genvar x = 0; x < W; x++) begin : gx
    for (genvar y = 0; y < H; y++) begin : gy
      omega_cell #(.X(x), .Y(y), .W(W), .H(H), .SLOTS(SLOTS), .QDEPTH(QDEPTH), .ROMSZ(ROMSZ),
                   .DIRSZ(DIRSZ), .DEPTH(DEPTH), .RDXSZ(RDXSZ), .MUT(MUT)) u_cell (
        .clk, .rst, .seed, .jitter, .stall, .pmsg, .fi, .spawn_k, .spawn_hint, .spawn_k2, .spawn_kp, .gov_b, .fork_dq, .gov_nb, .gov_l0, .rto_m1, .rgrad, .rsv, .lm_mode, .lm_hi, .lm_lo, .lm_rsv, .ilr, .lowmem, .ample(campl[x][y]), .link_local,
        .in_v(iv[x][y]), .in_f(inf[x][y]), .in_rdy(irdy[x][y]),
        .out_v(ov[x][y]), .out_f(of[x][y]), .out_rdy(ordy[x][y]),
        .idle(cidle[x][y]), .hungry(chung[x][y]), .nbr_hungry(nhung[x][y]), .roomy(croom[x][y]), .nbr_roomy(nroom[x][y]), .rdist(crd[x][y]), .nbr_rdist(nrd[x][y]), .ready(crdy[x][y]), .err(cerr[x][y]), .dump,
        .rom_req(rreq[x][y]), .rom_an(ran[x][y]), .rom_ar(rar[x][y]), .rom_gnt(rgnt[x][y]), .rom_dn(rdn[x][y]), .rom_dr(rdr[x][y]),
        .cfg_we(1'b0), .cfg_sel(2'd0), .cfg_a(16'd0), .cfg_d(128'd0), .st_inter(cint[x][y]),
        .adm_on, .adm_rb(a_rb), .hq_v((x == 0 && y == 0) ? a_hq_v : 1'b0), .hq_a(a_hq_a), .hq_b(a_hq_b), .hq_ack(c_hq_ack[x][y]),
        .hw_v((x == 0 && y == 0) ? a_hw_v : 1'b0), .hw_a(a_hw_a), .hw_d(a_hw_d), .hw_ack(c_hw_ack[x][y]),
        .mon_we(c_mwe[x][y]), .mon_we2(c_mwe2[x][y]), .mon_wa(c_mwa[x][y]), .mon_wa2(c_mwa2[x][y]),
        .mon_wd(c_mwd[x][y]), .mon_wd2(c_mwd2[x][y]), .free_n(c_fn[x][y]), .free_v(c_fv[x][y]), .tasks(c_tq[x][y]));
      assign nhung[x][y][0] = (y > 0)     ? chung[x][(y > 0) ? y-1 : 0] : 1'b0;
      assign nhung[x][y][1] = (x < W - 1) ? chung[(x < W - 1) ? x+1 : x][y] : 1'b0;
      assign nhung[x][y][2] = (y < H - 1) ? chung[x][(y < H - 1) ? y+1 : y] : 1'b0;
      assign nhung[x][y][3] = (x > 0)     ? chung[(x > 0) ? x-1 : 0][y] : 1'b0;
      assign nrd[x][y][0] = (y > 0)     ? crd[x][(y > 0) ? y-1 : 0] : 3'd7;
      assign nrd[x][y][1] = (x < W - 1) ? crd[(x < W - 1) ? x+1 : x][y] : 3'd7;
      assign nrd[x][y][2] = (y < H - 1) ? crd[x][(y < H - 1) ? y+1 : y] : 3'd7;
      assign nrd[x][y][3] = (x > 0)     ? crd[(x > 0) ? x-1 : 0][y] : 3'd7;
      assign nroom[x][y][0] = (y > 0)     ? croom[x][(y > 0) ? y-1 : 0] : 1'b0;
      assign nroom[x][y][1] = (x < W - 1) ? croom[(x < W - 1) ? x+1 : x][y] : 1'b0;
      assign nroom[x][y][2] = (y < H - 1) ? croom[x][(y < H - 1) ? y+1 : y] : 1'b0;
      assign nroom[x][y][3] = (x > 0)     ? croom[(x > 0) ? x-1 : 0][y] : 1'b0;
      // N neighbour (x, y-1): my in[N] <- its out[S]; my out[N] -> its in[S]
      if (y > 0) begin : gn
        assign iv[x][y][0] = ov[x][y-1][2]; assign inf[x][y][0] = of[x][y-1][2];
        assign ordy[x][y][0] = irdy[x][y-1][2];
      end else begin : gn0
        assign iv[x][y][0] = 1'b0; assign inf[x][y][0] = '0; assign ordy[x][y][0] = 1'b0;
      end
      if (y < H - 1) begin : gs
        assign iv[x][y][2] = ov[x][y+1][0]; assign inf[x][y][2] = of[x][y+1][0];
        assign ordy[x][y][2] = irdy[x][y+1][0];
      end else begin : gs0
        assign iv[x][y][2] = 1'b0; assign inf[x][y][2] = '0; assign ordy[x][y][2] = 1'b0;
      end
      if (x < W - 1) begin : ge
        assign iv[x][y][1] = ov[x+1][y][3]; assign inf[x][y][1] = of[x+1][y][3];
        assign ordy[x][y][1] = irdy[x+1][y][3];
      end else begin : ge0
        assign iv[x][y][1] = 1'b0; assign inf[x][y][1] = '0; assign ordy[x][y][1] = 1'b0;
      end
      if (x > 0) begin : gw
        assign iv[x][y][3] = ov[x-1][y][1]; assign inf[x][y][3] = of[x-1][y][1];
        assign ordy[x][y][3] = irdy[x-1][y][1];
      end else begin : gw0
        assign iv[x][y][3] = 1'b0; assign inf[x][y][3] = '0; assign ordy[x][y][3] = 1'b0;
      end
    end
  end

  // step 22: low-memory signal, an OR tree over the cells' ample bits (like the quiescence AND tree), registered
  logic campl [W][H];
  logic lowmem, any_ample;
  always_comb begin
    any_ample = 1'b0;
    for (int x = 0; x < W; x++)
      for (int y = 0; y < H; y++) any_ample |= campl[x][y];
  end
  always_ff @(posedge clk) begin
    if (rst) lowmem <= 1'b0;
    else lowmem <= !any_ample;
  end

  omega_adm #(.NJ(512), .RR(16), .NCELL(W * H), .MUT(MUT)) u_adm (
    .clk, .rst, .adm_on, .ready(all_ready), .cells_idle,
    .mon_we(c_mwe[0][0]), .mon_we2(c_mwe2[0][0]), .mon_wa(c_mwa[0][0]), .mon_wa2(c_mwa2[0][0]),
    .mon_wd(c_mwd[0][0]), .mon_wd2(c_mwd2[0][0]),
    .hq_v(a_hq_v), .hq_a(a_hq_a), .hq_b(a_hq_b), .hq_ack(c_hq_ack[0][0]),
    .hw_v(a_hw_v), .hw_a(a_hw_a), .hw_d(a_hw_d), .hw_ack(c_hw_ack[0][0]), .rbase(a_rb),
    .sum_free_n(sum_fn), .sum_free_v(sum_fv), .min_free(min_f), .adm_idle, .adm_err);

  always_comb begin
    all_idle = 1'b1; all_ready = 1'b1; any_err = '0; interactions = '0;
    cells_idle = 1'b1; sum_fn = '0; sum_fv = '0; min_f = 32'hFFFF_FFFF;
    for (int x = 0; x < W; x++)
      for (int y = 0; y < H; y++) begin
        cells_idle &= cidle[x][y];
        sum_fn += 32'(c_fn[x][y]); sum_fv += 32'(c_fv[x][y]);
        if (32'(c_fn[x][y]) < min_f) min_f = 32'(c_fn[x][y]);
        if (32'(c_fv[x][y]) < min_f) min_f = 32'(c_fv[x][y]);
        all_idle &= cidle[x][y];
        all_ready &= crdy[x][y];
        any_err |= cerr[x][y];
        interactions += cint[x][y];
      end
    all_idle &= adm_idle;
  end

`ifndef SYNTHESIS
  // step 29 (simulation only, SPEC 7.8): placement-certificate audit, on with +pcert=r (r = the ball radius, i.e.
  // rgrad).  Every cycle after initialisation: for every cell c, best(c) = max over cells d within r hops of
  // min(free_n(d), free_v(d)); a cycle in which some best(c) < lm_hi (no cell within r hops of c can be roomy)
  // counts as a violation.  Also the smallest best(c) seen and the peak of the mesh-wide used slots.  Reported by
  // the final block ("pcert_viol", "pcert_min", "pcert_used_n", "pcert_used_v"); without +pcert nothing runs.
  int pc_r; logic pc_on; longint pc_viol, pc_min, pc_un, pc_uv;
  initial begin
    pc_on = $value$plusargs("pcert=%d", pc_r); pc_viol = 0; pc_min = 64'd1 << 40; pc_un = 0; pc_uv = 0;
  end
  always @(posedge clk) if (pc_on && !rst && all_ready) begin
    longint bc, mf, un, uv;
    un = 0; uv = 0;
    for (int x = 0; x < W; x++)
      for (int y = 0; y < H; y++) begin
        un += longint'(SLOTS) - longint'(c_fn[x][y]); uv += longint'(SLOTS) - longint'(c_fv[x][y]);
        bc = 0;
        for (int u = 0; u < W; u++)
          for (int v = 0; v < H; v++)
            if ((u > x ? u - x : x - u) + (v > y ? v - y : y - v) <= pc_r) begin
              mf = longint'(c_fn[u][v]) < longint'(c_fv[u][v]) ? longint'(c_fn[u][v]) : longint'(c_fv[u][v]);
              if (mf > bc) bc = mf;
            end
        if (bc < pc_min) pc_min = bc;
        if (bc < longint'(lm_hi)) pc_viol++;
      end
    if (un > pc_un) pc_un = un;
    if (uv > pc_uv) pc_uv = uv;
  end
  final if (pc_on) $display("pcert_viol %0d\npcert_min %0d\npcert_used_n %0d\npcert_used_v %0d", pc_viol, pc_min, pc_un, pc_uv);
  // step 30 (simulation only, SPEC 7.9): task-stack audit, on with +tcert=A (A = the job's atom-atom interaction
  // count).  Every cycle after initialisation: E = stored task entries summed over all cells (stack, fork deque,
  // retry slot); a cycle with E > used_n + 2 * used_v + A (used: node / var slots in use, ballast included) counts as a
  // violation (the linear-reference argument of SPEC 7.9).  Also the peak of E, of any one cell's entries, and the
  // smallest slack.  Reported as "tcert_viol", "tcert_peak", "tcert_cell", "tcert_slack"; without +tcert nothing runs.
  // Joint-load audit (same switch): peaks of wn * used_n + 8 * used_v for wn = 0, 1, 2, 4, ..., 64 (the hull of SPEC 7.9
  // at lam = wn / 8), reported as "jcert_peak_<wn>".
  int tc_a; logic tc_on; longint tc_viol, tc_peak, tc_cell, tc_slack; longint jc_pk [8];
  initial begin
    tc_on = $value$plusargs("tcert=%d", tc_a); tc_viol = 0; tc_peak = 0; tc_cell = 0; tc_slack = 64'd1 << 40;
    for (int k = 0; k < 8; k++) jc_pk[k] = 0;
  end
  always @(posedge clk) if (tc_on && !rst && all_ready) begin
    longint e, un, uv, sl;
    e = 0; un = 0; uv = 0;
    for (int x = 0; x < W; x++)
      for (int y = 0; y < H; y++) begin
        e += longint'(c_tq[x][y]);
        if (longint'(c_tq[x][y]) > tc_cell) tc_cell = longint'(c_tq[x][y]);
        un += longint'(SLOTS) - longint'(c_fn[x][y]); uv += longint'(SLOTS) - longint'(c_fv[x][y]);
      end
    sl = un + 2 * uv + longint'(tc_a) - e;
    if (sl < 0) tc_viol++;
    if (sl < tc_slack) tc_slack = sl;
    if (e > tc_peak) tc_peak = e;
    for (int k = 0; k < 8; k++) begin
      longint wn, jv;
      wn = (k == 0) ? 0 : (longint'(1) << (k - 1));
      jv = wn * un + 8 * uv;
      if (jv > jc_pk[k]) jc_pk[k] = jv;
    end
  end
  final if (tc_on) begin
    $display("tcert_viol %0d\ntcert_peak %0d\ntcert_cell %0d\ntcert_slack %0d", tc_viol, tc_peak, tc_cell, tc_slack);
    for (int k = 0; k < 8; k++) $display("jcert_peak_%0d %0d", (k == 0) ? 0 : (1 << (k - 1)), jc_pk[k]);
  end
`endif
endmodule
