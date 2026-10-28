// TACHYON-Omega W x H mesh of active memory cells.  The only global wires are clock, reset,
// the verification knobs (seed / jitter / stall), the quiescence AND-tree (termination detection,
// SPEC 8) and the dump strobe used by the testbench to read the node RAMs back.
`include "omega_defs.svh"
module omega_mesh #(
  parameter int W = 2, parameter int H = 2, parameter int SLOTS = 1024, parameter int QDEPTH = 1024,
  parameter int ROMSZ = 4096, parameter int DIRSZ = 256, parameter int DEPTH = 4, parameter int RDXSZ = 2048,
  parameter logic [255:0] MUT = '0
) (
  input  logic        clk, rst,
  input  logic [31:0] seed,
  input  logic [7:0]  jitter, stall, pmsg,
  input  logic [7:0]  fi,
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

  for (genvar x = 0; x < W; x++) begin : gx
    for (genvar y = 0; y < H; y++) begin : gy
      omega_cell #(.X(x), .Y(y), .W(W), .H(H), .SLOTS(SLOTS), .QDEPTH(QDEPTH), .ROMSZ(ROMSZ),
                   .DIRSZ(DIRSZ), .DEPTH(DEPTH), .RDXSZ(RDXSZ), .MUT(MUT)) u_cell (
        .clk, .rst, .seed, .jitter, .stall, .pmsg, .fi,
        .in_v(iv[x][y]), .in_f(inf[x][y]), .in_rdy(irdy[x][y]),
        .out_v(ov[x][y]), .out_f(of[x][y]), .out_rdy(ordy[x][y]),
        .idle(cidle[x][y]), .hungry(chung[x][y]), .nbr_hungry(nhung[x][y]), .roomy(croom[x][y]), .nbr_roomy(nroom[x][y]), .ready(crdy[x][y]), .err(cerr[x][y]), .dump,
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
