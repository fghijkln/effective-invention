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
  input  logic        fork_dq,             // step 14 fork deque + oldest-fork give (SPEC 5.3; 0 = step 13)
  input  logic [3:0]  gov_nb,              // step 14 governor: relax with a hungry neighbour (0 = off)
  input  logic [2:0]  gov_l0,              //   governor reset level
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
  logic  crdy [W][H];
  logic [3:0]  cerr [W][H];
  logic [31:0] cint [W][H];
  logic        rreq [W][H];
  logic [15:0] ran  [W][H];
  logic [15:0] rar  [W][H];
  logic        rgnt [W][H];
  logic [511:0] rdn [W][H];
  logic [511:0] rdr [W][H];

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
        .clk, .rst, .seed, .jitter, .stall, .pmsg, .fi, .spawn_k, .spawn_hint, .spawn_k2, .spawn_kp, .gov_b, .fork_dq, .gov_nb, .gov_l0, .link_local,
        .in_v(iv[x][y]), .in_f(inf[x][y]), .in_rdy(irdy[x][y]),
        .out_v(ov[x][y]), .out_f(of[x][y]), .out_rdy(ordy[x][y]),
        .idle(cidle[x][y]), .hungry(chung[x][y]), .nbr_hungry(nhung[x][y]), .roomy(croom[x][y]), .nbr_roomy(nroom[x][y]), .ready(crdy[x][y]), .err(cerr[x][y]), .dump,
        .rom_req(rreq[x][y]), .rom_an(ran[x][y]), .rom_ar(rar[x][y]), .rom_gnt(rgnt[x][y]), .rom_dn(rdn[x][y]), .rom_dr(rdr[x][y]),
        .cfg_we(1'b0), .cfg_sel(2'd0), .cfg_a(16'd0), .cfg_d(128'd0), .st_inter(cint[x][y]));
      assign nhung[x][y][0] = (y > 0)     ? chung[x][(y > 0) ? y-1 : 0] : 1'b0;
      assign nhung[x][y][1] = (x < W - 1) ? chung[(x < W - 1) ? x+1 : x][y] : 1'b0;
      assign nhung[x][y][2] = (y < H - 1) ? chung[x][(y < H - 1) ? y+1 : y] : 1'b0;
      assign nhung[x][y][3] = (x > 0)     ? chung[(x > 0) ? x-1 : 0][y] : 1'b0;
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

  always_comb begin
    all_idle = 1'b1; all_ready = 1'b1; any_err = '0; interactions = '0;
    for (int x = 0; x < W; x++)
      for (int y = 0; y < H; y++) begin
        all_idle &= cidle[x][y];
        all_ready &= crdy[x][y];
        any_err |= cerr[x][y];
        interactions += cint[x][y];
      end
  end
endmodule
