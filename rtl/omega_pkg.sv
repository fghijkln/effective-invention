// TACHYON-Omega: shared encodings (must match omega/ports.py and SPEC.md)
package omega_pkg;
  localparam logic [3:0] T_NONE = 4'd0, T_VAR = 4'd1, T_REF = 4'd2, T_ERA = 4'd3, T_NUM = 4'd4,
                         T_CON = 4'd5, T_DUP = 4'd6, T_OPR = 4'd7, T_SWI = 4'd8;

  localparam logic [1:0] M_LINK = 2'd0, M_NODE = 2'd1, M_SPAWN = 2'd2;
  localparam logic [1:0] K_LINK = 2'd0, K_SPAWN = 2'd2;   // task-stack entry kinds

  typedef struct packed {
    logic [1:0]  kind;
    logic [3:0]  dx;
    logic [3:0]  dy;
    logic [63:0] p3;
    logic [63:0] p2;
    logic [63:0] p1;
    logic [63:0] p0;
  } flit_t;

  function automatic logic [3:0]  ptag(input logic [63:0] p);  return p[63:60]; endfunction
  function automatic logic [15:0] plab(input logic [63:0] p);  return p[59:44]; endfunction
  function automatic logic [31:0] pval(input logic [63:0] p);  return p[31:0];  endfunction
  function automatic logic [3:0]  px(input logic [63:0] p);    return p[23:20]; endfunction
  function automatic logic [3:0]  py(input logic [63:0] p);    return p[19:16]; endfunction
  function automatic logic [11:0] pslot(input logic [63:0] p); return p[11:0];  endfunction
  function automatic logic is_var(input logic [63:0] p);  return p[63:60] == T_VAR; endfunction
  function automatic logic is_node(input logic [63:0] p);
    return p[63:60] == T_CON || p[63:60] == T_DUP || p[63:60] == T_OPR || p[63:60] == T_SWI;
  endfunction
  function automatic logic [63:0] mkp(input logic [3:0] t, input logic [15:0] l, input logic [31:0] v);
    return {t, l, 12'd0, v};
  endfunction
  // ---- owner capabilities (SPEC 12) ----
  localparam logic [3:0] OWN_FREE = 4'hF;
  localparam logic [1:0] TR_CROSS = 2'd1, TR_FORGED = 2'd2, TR_OOB = 2'd3;
  function automatic logic [3:0] pown(input logic [63:0] p); return p[43:40]; endfunction
  function automatic logic is_cap(input logic [63:0] p);
    return p[63:60] == T_VAR || p[63:60] == T_REF || is_node(p);
  endfunction
  function automatic logic [63:0] mkpo(input logic [3:0] t, input logic [15:0] l, input logic [3:0] o, input logic [31:0] v);
    return {t, l, o, 8'd0, v};
  endfunction
  function automatic logic [63:0] withown(input logic [63:0] p, input logic [3:0] o);
    return {p[63:44], o, p[39:0]};
  endfunction
  function automatic logic [63:0] withpay(input logic [63:0] p, input logic [31:0] v);
    return {p[63:32], v};
  endfunction
  function automatic logic [31:0] mkaddr(input logic [3:0] x, input logic [3:0] y, input logic [11:0] s);
    return {8'd0, x, y, 4'd0, s};
  endfunction

  function automatic logic [31:0] alu(input logic [3:0] op, input logic [31:0] a, input logic [31:0] b);
    case (op)
      4'd0:  return a + b;
      4'd1:  return a - b;
      4'd2:  return a * b;
      4'd3:  return (b == 0) ? 32'd0 : a / b;
      4'd4:  return (b == 0) ? 32'd0 : a % b;
      4'd5:  return {31'd0, a == b};
      4'd6:  return {31'd0, a != b};
      4'd7:  return {31'd0, a < b};
      4'd8:  return {31'd0, a > b};
      4'd9:  return {31'd0, a <= b};
      4'd10: return {31'd0, a >= b};
      4'd11: return a & b;
      4'd12: return a | b;
      4'd13: return a ^ b;
      4'd14: return a << b[4:0];
      default: return a >> b[4:0];
    endcase
  endfunction

  function automatic logic [31:0] xorshift(input logic [31:0] s);
    logic [31:0] t;
    t = s ^ (s << 13);
    t = t ^ (t >> 17);
    return t ^ (t << 5);
  endfunction
endpackage
