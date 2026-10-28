// TACHYON-Omega 5-port mesh router (N, E, S, W, local), XY dimension-order routing.
// Each neighbour input has a DEPTH-entry FIFO; the local input is the cell's outbox (owned by the
// cell, popped through l_pop).  The ejection FIFO feeds the cell's rewrite engine.
// Random arbitration and link jitter come from an xorshift LFSR so that the verification can
// sweep message timings (strong confluence => the normal form must not change).
`include "omega_defs.svh"
module omega_router #(
  parameter int X = 0, parameter int Y = 0, parameter int DEPTH = 4
) (
  input  logic        clk, rst,
  input  logic [31:0] seed,
  input  logic [7:0]  jitter,          // probability/256 that a ready output is held this cycle
  // neighbour inputs (index 0 N, 1 E, 2 S, 3 W)
  input  logic [3:0]  in_v,
  input  flit_t [3:0] in_f,
  output logic [3:0]  in_rdy,
  // neighbour outputs
  output logic [3:0]  out_v,
  output flit_t [3:0] out_f,
  input  logic [3:0]  out_rdy,
  // local outbox (FIFO lives in the cell)
  input  logic        l_v,
  input  flit_t       l_f,
  output logic        l_pop,
  // ejection to the engine
  output logic        ej_v,
  output flit_t       ej_f,
  input  logic        ej_pop,
  output logic        busy
);
  `include "omega_funcs.svh"
  localparam int AW = $clog2(DEPTH);
  flit_t [3:0][DEPTH-1:0] q;                 // input FIFOs (flip-flops)
  logic [3:0][AW:0]   cnt;
  logic [3:0][AW-1:0] hd;
  flit_t [DEPTH-1:0]  ejq;
  logic [AW:0] ejc;
  logic [AW-1:0] ejh;
  logic [31:0] rng;

  // heads of the 5 inputs
  logic [4:0]       hv;
  flit_t [4:0]      hf;
  logic [4:0][2:0]  dir;
  always_comb begin
    for (int i = 0; i < 4; i++) begin
      hv[i] = cnt[i] != 0;
      hf[i] = q[i][hd[i]];
    end
    hv[4] = l_v;
    hf[4] = l_f;
    for (int i = 0; i < 5; i++) begin
      if (32'(hf[i][263:260]) > X)      dir[i] = 3'd1;
      else if (32'(hf[i][263:260]) < X) dir[i] = 3'd3;
      else if (32'(hf[i][259:256]) > Y) dir[i] = 3'd2;
      else if (32'(hf[i][259:256]) < Y) dir[i] = 3'd0;
      else                         dir[i] = 3'd4;
    end
  end

  // output arbitration: rotating start chosen by the LFSR
  logic [4:0]      grant;      // input i moves this cycle
  logic [4:0][2:0] sel;        // output o takes input sel[o]
  logic [4:0]      go;
  always_comb begin
    for (int i = 0; i < 5; i++) grant[i] = 1'b0;
    for (int o = 0; o < 5; o++) begin
      logic orq;
      logic hold;
      logic [2:0] start;
      go[o] = 1'b0; sel[o] = 3'd0;
      orq = (o == 4) ? (ejc < (AW+1)'(DEPTH)) : out_rdy[o % 4];
      hold = (rng[8*(o%4) +: 8] < jitter) && (jitter != 0);
      start = rng[o*3 +: 3];
      if (start >= 3'd5) start = start - 3'd5;       // 0..4 (small-width modulo, no divider)
      for (int k = 0; k < 5; k++) begin
        logic [3:0] i;
        i = 4'(start) + 4'(k);
        if (i >= 4'd5) i = i - 4'd5;
        if (!go[o] && hv[i] && dir[i] == 3'(o) && orq && !hold) begin
          go[o] = 1'b1; sel[o] = 3'(i); grant[i] = 1'b1;
        end
      end
    end
    for (int o = 0; o < 4; o++) begin
      out_v[o] = go[o];
      out_f[o] = hf[sel[o]];
    end
    l_pop = grant[4];
    for (int i = 0; i < 4; i++) in_rdy[i] = cnt[i] < (AW+1)'(DEPTH);
    ej_v = ejc != 0;
    ej_f = ejq[ejh];
    busy = (cnt[0] != 0) || (cnt[1] != 0) || (cnt[2] != 0) || (cnt[3] != 0) || (ejc != 0);
  end

  always_ff @(posedge clk) begin
    if (rst) begin
      for (int i = 0; i < 4; i++) begin cnt[i] <= '0; hd[i] <= '0; end
      ejc <= '0; ejh <= '0;
      rng <= seed ^ (32'h9E3779B9 * (X * 16 + Y + 1)) ^ 32'h1;
    end else begin
      rng <= xorshift(rng);
      for (int i = 0; i < 4; i++) begin
        logic push, pop;
        push = in_v[i] && in_rdy[i];
        pop = grant[i];
        if (push) q[i][AW'(hd[i] + AW'(cnt[i]))] <= in_f[i];
        if (pop) hd[i] <= hd[i] + 1'b1;
        cnt[i] <= cnt[i] + (AW+1)'(push) - (AW+1)'(pop);
      end
      begin
        logic push, pop;
        push = go[4];
        pop = ej_pop && ejc != 0;
        if (push) ejq[AW'(ejh + AW'(ejc))] <= hf[sel[4]];
        if (pop) ejh <= ejh + 1'b1;
        ejc <= ejc + (AW+1)'(push) - (AW+1)'(pop);
      end
    end
  end
endmodule
