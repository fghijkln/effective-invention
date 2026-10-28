// TACHYON-Omega: shared encodings (must match omega/ports.py and SPEC.md).
// File-scope typedef + constants (included by every RTL file; written in the SystemVerilog subset that
// both Verilator and Yosys' native front end accept, so one source is simulated and synthesised).
`ifndef OMEGA_DEFS_SVH
`define OMEGA_DEFS_SVH
localparam logic [3:0] T_NONE = 4'd0, T_VAR = 4'd1, T_REF = 4'd2, T_ERA = 4'd3, T_NUM = 4'd4,
                       T_CON = 4'd5, T_DUP = 4'd6, T_OPR = 4'd7, T_SWI = 4'd8;
localparam logic [1:0] M_LINK = 2'd0, M_NODE = 2'd1, M_SPAWN = 2'd2;
localparam logic [1:0] K_LINK = 2'd0, K_SPAWN = 2'd2;   // task-stack entry kinds
// owner capabilities (SPEC 12)
localparam logic [3:0] OWN_FREE = 4'hF;
localparam logic [1:0] TR_CROSS = 2'd1, TR_FORGED = 2'd2, TR_OOB = 2'd3;

typedef struct packed {
  logic [1:0]  kind;
  logic [3:0]  dx;
  logic [3:0]  dy;
  logic [63:0] p3;
  logic [63:0] p2;
  logic [63:0] p1;
  logic [63:0] p0;
} flit_t;
`endif
