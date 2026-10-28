// TACHYON-Omega: helper functions, included inside each module (Yosys' native front end does not
// support functions in packages or `return`, so they are written as assignments to the function name).
function automatic logic [3:0]  ptag(input logic [63:0] p);  ptag = p[63:60]; endfunction
function automatic logic [15:0] plab(input logic [63:0] p);  plab = p[59:44]; endfunction
function automatic logic [31:0] pval(input logic [63:0] p);  pval = p[31:0];  endfunction
function automatic logic [3:0]  px(input logic [63:0] p);    px = p[23:20]; endfunction
function automatic logic [3:0]  py(input logic [63:0] p);    py = p[19:16]; endfunction
function automatic logic [11:0] pslot(input logic [63:0] p); pslot = p[11:0];  endfunction
function automatic logic [3:0]  pown(input logic [63:0] p);  pown = p[43:40]; endfunction
function automatic logic is_var(input logic [63:0] p);  is_var = p[63:60] == T_VAR; endfunction
function automatic logic is_node(input logic [63:0] p);
  is_node = p[63:60] == T_CON || p[63:60] == T_DUP || p[63:60] == T_OPR || p[63:60] == T_SWI;
endfunction
function automatic logic is_cap(input logic [63:0] p);
  is_cap = p[63:60] == T_VAR || p[63:60] == T_REF || p[63:60] == T_CON || p[63:60] == T_DUP ||
           p[63:60] == T_OPR || p[63:60] == T_SWI;
endfunction
function automatic logic [63:0] mkp(input logic [3:0] t, input logic [15:0] l, input logic [31:0] v);
  mkp = {t, l, 12'd0, v};
endfunction
function automatic logic [63:0] mkpo(input logic [3:0] t, input logic [15:0] l, input logic [3:0] o, input logic [31:0] v);
  mkpo = {t, l, o, 8'd0, v};
endfunction
function automatic logic [63:0] withown(input logic [63:0] p, input logic [3:0] o);
  withown = {p[63:44], o, p[39:0]};
endfunction
function automatic logic [63:0] withpay(input logic [63:0] p, input logic [31:0] v);
  withpay = {p[63:32], v};
endfunction
function automatic logic [31:0] mkaddr(input logic [3:0] x, input logic [3:0] y, input logic [11:0] s);
  mkaddr = {8'd0, x, y, 4'd0, s};
endfunction
function automatic logic [31:0] alu(input logic [3:0] op, input logic [31:0] a, input logic [31:0] b);
  case (op)
    4'd0:  alu = a + b;
    4'd1:  alu = a - b;
    4'd2:  alu = a * b;
    4'd3:  alu = (b == 0) ? 32'd0 : a / b;
    4'd4:  alu = (b == 0) ? 32'd0 : a % b;
    4'd5:  alu = {31'd0, a == b};
    4'd6:  alu = {31'd0, a != b};
    4'd7:  alu = {31'd0, a < b};
    4'd8:  alu = {31'd0, a > b};
    4'd9:  alu = {31'd0, a <= b};
    4'd10: alu = {31'd0, a >= b};
    4'd11: alu = a & b;
    4'd12: alu = a | b;
    4'd13: alu = a ^ b;
    4'd14: alu = a << b[4:0];
    default: alu = a >> b[4:0];
  endcase
endfunction
function automatic logic [31:0] xorshift(input logic [31:0] s);
  logic [31:0] t;
  t = s ^ (s << 13);
  t = t ^ (t >> 17);
  xorshift = t ^ (t << 5);
endfunction
