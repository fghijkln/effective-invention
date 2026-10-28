// TACHYON-Omega cluster definition ROM (step 7): one node-template ROM + one redex-template ROM shared
// by the NC cells of a cluster (SPEC 5.6).
//
// NP read ports (1 or 2).  Every cycle the arbiter grants up to NP of the requesting cells, starting
// from a rotating priority pointer (round robin: a requester waits at most ceil(NC / NP) - 1 cycles).
// A granted cell's node-template and redex-template addresses are read on the same port (the EXPAND
// step consumes node i and redex i together); the data is registered (synchronous ROM read) and
// steered back to the cell one cycle later.  A cell that is not granted simply re-requests: its
// EXPAND step holds until the data it asked for has arrived (`rom_v` in omega_cell).
// Each ROM word holds a PAIR of template entries (the loader aligns every definition to an even
// entry), so one grant feeds two EXPAND cycles of the requesting cell.
// Both arrays are written so that synthesis infers NP-read-port ROM macros (1R when NP = 1) with one
// loader write port.
`include "omega_defs.svh"
module omega_rom #(
  parameter int NC = 1, parameter int NP = 1,
  parameter int ROMSZ = 4096, parameter int RDXSZ = 2048,
  parameter int CX = 0, parameter int CY = 0,         // cluster index
  parameter logic [255:0] MUT = '0                    // mutation-testing knobs (bit 29)
) (
  input  logic                 clk, rst,
  input  logic [NC-1:0]        req,
  input  logic [NC-1:0][15:0]  an,          // node-template PAIR address per cell
  input  logic [NC-1:0][15:0]  ar,          // redex-template pair address per cell
  output logic [NC-1:0]        gnt,
  output logic [NC-1:0][255:0] dn,          // read data: a pair of entries (valid the cycle after the grant)
  output logic [NC-1:0][255:0] dr,
  input  logic                 cfg_we,
  input  logic [1:0]           cfg_sel,     // 0 = node ROM, 1 = redex ROM
  input  logic [15:0]          cfg_a,
  input  logic [255:0]         cfg_d
);
  localparam int RB = $clog2(ROMSZ / 2);       // ROM words hold pairs of template entries
  localparam int RRB = $clog2(RDXSZ / 2);
  localparam int CB = (NC > 1) ? $clog2(NC) : 1;
  localparam int PB = (NP > 1) ? $clog2(NP) : 1;

  logic [255:0] romn [ROMSZ / 2];
  logic [255:0] romr [RDXSZ / 2];
`ifndef SYNTHESIS
  string imgdir;
  initial begin
    if (!$value$plusargs("img=%s", imgdir)) imgdir = "build/img";
    $readmemh($sformatf("%s/romn.hex", imgdir), romn);
    $readmemh($sformatf("%s/romr.hex", imgdir), romr);
  end
`endif

  // ---- round-robin arbiter: up to NP grants per cycle ----
  logic [CB-1:0] ptr;
  logic [NP-1:0] pv;                       // port p is used this cycle
  logic [NP-1:0][CB-1:0] pc;               // ... by cell pc[p]
  logic [CB-1:0] last;
  always_comb begin
    int n;
    gnt = '0; pv = '0; pc = '0; last = ptr; n = 0;
    for (int k = 0; k < NC; k++) begin
      int c;
      c = (32'(ptr) + k) % NC;
      if (req[c] && n < NP) begin
        gnt[c] = 1'b1; pv[n] = 1'b1; pc[n] = CB'(c); last = CB'(c); n = n + 1;
      end else if (req[c] && MUT[29]) gnt[c] = 1'b1;     // mutant: grant beyond the port count
    end
  end

  // ---- NP synchronous read ports ----
  logic [NP-1:0][255:0] pdn, pdr;
  logic [NC-1:0][PB-1:0] psel;             // which port serves cell c (registered with the read)
  always_ff @(posedge clk) begin
    if (rst) begin ptr <= '0; psel <= '0; end
    else if (pv != 0) ptr <= (32'(last) + 1 >= NC) ? '0 : CB'(32'(last) + 1);
    for (int p = 0; p < NP; p++) begin
      pdn[p] <= romn[RB'(an[pc[p]])];
      pdr[p] <= romr[RRB'(ar[pc[p]])];
    end
    for (int p = 0; p < NP; p++) if (pv[p]) psel[pc[p]] <= PB'(p);
    if (cfg_we && cfg_sel == 2'd0) romn[RB'(cfg_a)] <= cfg_d;
    if (cfg_we && cfg_sel == 2'd1) romr[RRB'(cfg_a)] <= cfg_d;
  end
  always_comb
    for (int c = 0; c < NC; c++) begin dn[c] = pdn[psel[c]]; dr[c] = pdr[psel[c]]; end
endmodule
