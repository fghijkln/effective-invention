// TACHYON-Omega active memory cell: node RAM + var RAM (with shadow allocation tags), free stacks,
// LIFO task stack, definition ROM (read-only templates, replicated per cell), local rewrite engine
// and a mesh router.  There is no program counter and no instruction stream: the engine only
// ever reacts to (a) a task on its own stack or (b) a message that arrived from a neighbour.
// See SPEC.md section 6 for the state machine and section 3 for the rule table.
module omega_cell import omega_pkg::*; #(
  parameter int X = 0, parameter int Y = 0, parameter int W = 1, parameter int H = 1,
  parameter int SLOTS = 1024, parameter int QDEPTH = 1024,
  parameter int ROMSZ = 4096, parameter int DIRSZ = 256, parameter int DEPTH = 4,
  parameter logic [255:0] MUT = '0          // mutation-testing knobs (0 = correct design)
) (
  input  logic        clk, rst,
  input  logic [31:0] seed,
  input  logic [7:0]  jitter, stall, pmsg,
  input  logic [7:0]  fi,                  // fault injection: bit 0 = sender skips the cross-owner check
  input  logic        in_v [4],
  input  flit_t       in_f [4],
  output logic        in_rdy [4],
  output logic        out_v [4],
  output flit_t       out_f [4],
  input  logic        out_rdy [4],
  output logic        idle,
  output logic        hungry,              // to neighbours: no local work (demand-driven spawn)
  input  logic        nbr_hungry [4],      // from neighbours N, E, S, W
  output logic        ready,               // initialisation finished
  output logic [3:0]  err,
  input  logic        dump,
  output logic [31:0] st_inter
);
  localparam int SB = $clog2(SLOTS);
  localparam int QB = $clog2(QDEPTH);
  localparam int OB = $clog2(DEPTH);

  typedef enum logic [3:0] {S_INIT, S_IDLE, S_LINK, S_PUSH, S_SPAWN, S_EXPH, S_EXPN, S_EXPR, S_HALT} st_t;
  st_t state;

  // ---------------- storage ----------------
  logic [127:0] node_mem [SLOTS];       // {aux2, aux1}
  logic         nalloc   [SLOTS];       // shadow tag: slot holds a live node
  logic [63:0]  var_mem  [SLOTS];       // substitution (0 = NONE); free slots always hold NONE
  logic         valloc   [SLOTS];       // initial allocation (image only)
  logic [3:0]   nown     [SLOTS];       // shadow owner tag of each node slot (OWN_FREE = free)
  logic [3:0]   vown     [SLOTS];       // shadow owner tag of each var slot
  logic [SB-1:0] nstack  [SLOTS];
  logic [SB-1:0] vstack  [SLOTS];
  logic [SB:0]   ntop, vtop;
  logic [129:0] tq [QDEPTH];            // task stack {kind, b, a}
  logic [QB:0]  qtop;
  logic [15:0]  qinit [1];
  logic [127:0] rom [ROMSZ];            // definition templates {b, a}
  logic [15:0]  dirm [DIRSZ];
  flit_t        ob [DEPTH];             // outbox (router local input)
  logic [OB:0]  ob_cnt;
  logic [OB-1:0] ob_hd;

  string imgdir, outdir;
  initial begin
    if (!$value$plusargs("img=%s", imgdir)) imgdir = "build/img";
    if (!$value$plusargs("out=%s", outdir)) outdir = imgdir;
    $readmemh($sformatf("%s/node_%0d_%0d.hex", imgdir, X, Y), node_mem);
    $readmemh($sformatf("%s/nalloc_%0d_%0d.hex", imgdir, X, Y), nalloc);
    $readmemh($sformatf("%s/var_%0d_%0d.hex", imgdir, X, Y), var_mem);
    $readmemh($sformatf("%s/valloc_%0d_%0d.hex", imgdir, X, Y), valloc);
    $readmemh($sformatf("%s/nown_%0d_%0d.hex", imgdir, X, Y), nown);
    $readmemh($sformatf("%s/vown_%0d_%0d.hex", imgdir, X, Y), vown);
    $readmemh($sformatf("%s/queue_%0d_%0d.hex", imgdir, X, Y), tq);
    $readmemh($sformatf("%s/qcount_%0d_%0d.hex", imgdir, X, Y), qinit);
    $readmemh($sformatf("%s/rom.hex", imgdir), rom);
    $readmemh($sformatf("%s/dir.hex", imgdir), dirm);
  end

  // ---------------- router ----------------
  logic  l_pop, ej_v, ej_pop, rbusy;
  flit_t ej_f;
  omega_router #(.X(X), .Y(Y), .DEPTH(DEPTH)) u_rt (
    .clk, .rst, .seed, .jitter, .in_v, .in_f, .in_rdy, .out_v, .out_f, .out_rdy,
    .l_v(ob_cnt != 0), .l_f(ob[ob_hd]), .l_pop, .ej_v, .ej_f, .ej_pop, .busy(rbusy));

  // spawn targets: index 0 = self, then existing neighbours in E S W N order
  localparam int HAS_E = (X < W - 1) ? 1 : 0, HAS_S = (Y < H - 1) ? 1 : 0;
  localparam int HAS_W = (X > 0) ? 1 : 0,     HAS_N = (Y > 0) ? 1 : 0;
  localparam int NT = 1 + HAS_E + HAS_S + HAS_W + HAS_N;
  logic [3:0] tx [5], ty [5];
  always_comb begin
    int k;
    k = 1;
    tx[0] = 4'(X); ty[0] = 4'(Y);
    for (int i = 1; i < 5; i++) begin tx[i] = 4'(X); ty[i] = 4'(Y); end
    if (HAS_E != 0) begin tx[k] = 4'(X + 1); ty[k] = 4'(Y); k++; end
    if (HAS_S != 0) begin tx[k] = 4'(X); ty[k] = 4'(Y + 1); k++; end
    if (HAS_W != 0) begin tx[k] = 4'(X - 1); ty[k] = 4'(Y); k++; end
    if (HAS_N != 0) begin tx[k] = 4'(X); ty[k] = 4'(Y - 1); k++; end
  end

  // demand-driven spawn target: first hungry existing neighbour in rotating order (N E S W)
  localparam logic [3:0] EXISTS = {HAS_W != 0, HAS_S != 0, HAS_E != 0, HAS_N != 0};
  logic       hv_found;
  logic [1:0] hv_dir;
  logic [1:0] hrot;
  always_comb begin
    hv_found = 1'b0; hv_dir = 2'd0;
    for (int k = 0; k < 4; k++) begin
      logic [1:0] d;
      d = 2'(hrot + 2'(k));
      if (!hv_found && EXISTS[d] && nbr_hungry[d]) begin hv_found = 1'b1; hv_dir = d; end
    end
  end
  function automatic logic [3:0] dir_x(input logic [1:0] d);
    return (d == 2'd1) ? 4'(X + 1) : (d == 2'd3) ? 4'(X - 1) : 4'(X);
  endfunction
  function automatic logic [3:0] dir_y(input logic [1:0] d);
    return (d == 2'd0) ? 4'(Y - 1) : (d == 2'd2) ? 4'(Y + 1) : 4'(Y);
  endfunction

  // ---------------- engine registers ----------------
  logic [63:0] ra, rb;
  logic [63:0] pa [4], pbv [4];
  logic [2:0]  pidx;
  logic [15:0] sp_ref;
  logic [3:0]  sp_own, ex_own;
  logic [31:0] st_traps, tr_addr;
  logic [1:0]  tr_reason;
  logic [3:0]  tr_owner;
  logic [47:0] tr_mask;                 // (reason, owner) pairs seen: bit (reason-1)*16 + owner
  logic [63:0] sp_x;
  logic [2:0]  rr;
  logic [15:0] ex_base;
  logic [7:0]  ex_nn, ex_nv, ex_nr, ex_i;
  logic [63:0] ex_root, ex_x;
  logic [SB:0] nb, vb;
  logic [31:0] erng;
  logic [SB:0] init_i;
  logic [SB:0] st_minfn, st_minfv;
  logic [31:0] cyc, st_busy, st_retry, st_msg0, st_msg1, st_msg2, st_maxq, st_links, st_tasks;

  function automatic logic local_p(input logic [63:0] p);
    return px(p) == 4'(X) && py(p) == 4'(Y);
  endfunction
  function automatic logic [31:0] here(input logic [SB-1:0] s);
    return mkaddr(4'(X), 4'(Y), 12'(s));
  endfunction
  // T3: pointer outside the fabric (or malformed address bits)
  function automatic logic oob(input logic [63:0] p);
    if (MUT[18]) return 1'b0;
    return 32'(px(p)) >= W || 32'(py(p)) >= H || 32'(pslot(p)) >= SLOTS || p[31:24] != 8'd0 || p[15:12] != 4'd0;
  endfunction
  function automatic logic leaves(input logic [63:0] p);   // pointer is remote or out of bounds
    return oob(p) || !local_p(p);
  endfunction
  // T1: two capabilities of different owners meet
  function automatic logic [63:0] lowown(input logic [63:0] a, input logic [63:0] b);  // CROSS trap blames the lower owner id
    return (pown(a) < pown(b)) ? a : b;
  endfunction
  function automatic logic xown(input logic [63:0] a, input logic [63:0] b);
    if (MUT[17]) return 1'b0;
    return is_cap(a) && is_cap(b) && pown(a) != pown(b);
  endfunction

  // ---------------- source selection (combinational, also drives the ejection pop) ----------------
  logic can_send, msg_ok, q_ok, stall_now, pick_msg, take_msg, take_q;
  always_comb begin
    can_send  = ob_cnt < (OB+1)'(DEPTH);
    msg_ok    = ej_v && !(ej_f.kind == M_NODE && ntop == 0);
    q_ok      = qtop != 0;
    stall_now = (stall != 0) && (erng[7:0] < stall);
    pick_msg  = msg_ok && (!q_ok || !can_send || (erng[15:8] < pmsg));
    take_msg  = (state == S_IDLE) && !stall_now && pick_msg;
    take_q    = (state == S_IDLE) && !stall_now && q_ok && !pick_msg;
    ej_pop    = take_msg;
    idle      = (state == S_IDLE) && (qtop == 0) && !ej_v && (ob_cnt == 0) && (!rbusy || MUT[15]);
    ready     = state != S_INIT;
    hungry    = (state == S_IDLE) && (qtop == 0) && !ej_v;
  end

  // translation of a template port during EXPAND
  function automatic logic [63:0] tr(input logic [63:0] p);
    logic [3:0] t, o;
    t = ptag(p);
    o = MUT[19] ? 4'd0 : ex_own;
    if (p[39]) return {p[63:44], o, 1'b0, p[38:0]};          // absolute (forged) pointer: no relocation
    if (t == T_VAR) return mkpo(T_VAR, 16'd0, o, here(vstack[SB'(vb - 1 - (SB+1)'(pval(p)))]));
    if (t == T_CON || t == T_DUP || t == T_OPR || t == T_SWI)
      return withown(withpay(p, here(nstack[SB'(nb - 1 - (SB+1)'(pval(p)))])), o);
    if (t == T_REF) return withown(p, o);
    return p;
  endfunction

  always_ff @(posedge clk) begin
    if (rst) begin
      state <= S_INIT;
      ntop <= '0; vtop <= '0; init_i <= (SB+1)'(SLOTS);
      qtop <= (QB+1)'(qinit[0]);
      ob_cnt <= '0; ob_hd <= '0;
      err <= '0; rr <= '0; hrot <= 2'(X + Y);
      erng <= seed ^ (32'h85EBCA6B * (X * 16 + Y + 7)) ^ 32'h2;
      cyc <= '0; st_inter <= '0; st_busy <= '0; st_retry <= '0; st_msg0 <= '0; st_msg1 <= '0;
      st_msg2 <= '0; st_maxq <= '0; st_links <= '0; st_tasks <= '0;
      st_minfn <= '1; st_minfv <= '1;
      st_traps <= '0; tr_addr <= '0; tr_reason <= '0; tr_owner <= '0; tr_mask <= '0;
    end else begin
      // per-cycle temporaries
      logic snd; flit_t sf;
      logic qp; logic [129:0] qe;
      logic [1:0] nfc; logic [SB-1:0] nf0, nf1;
      logic tp; logic [1:0] tpr; logic [63:0] tpp;
      snd = 1'b0; sf = '0; qp = 1'b0; qe = '0; nfc = 2'd0; nf0 = '0; nf1 = '0;
      tp = 1'b0; tpr = '0; tpp = '0;
      erng <= xorshift(erng);
      if (state != S_INIT && ntop < st_minfn) st_minfn <= ntop;
      if (state != S_INIT && vtop < st_minfv) st_minfv <= vtop;
      if (state != S_INIT) cyc <= cyc + 1;
      if (state != S_IDLE && state != S_INIT && state != S_HALT) st_busy <= st_busy + 1;

      case (state)
        // ------------------------------------------------------------------ init: build free stacks
        S_INIT: begin
          logic [SB-1:0] i;
          i = SB'(init_i - 1);
          if (!nalloc[i]) begin nstack[ntop[SB-1:0]] <= i; end
          if (!valloc[i]) begin vstack[vtop[SB-1:0]] <= i; end
          ntop <= ntop + (SB+1)'(!nalloc[i]);
          vtop <= vtop + (SB+1)'(!valloc[i]);
          init_i <= init_i - 1;
          if (init_i == 1) state <= S_IDLE;
        end

        // ------------------------------------------------------------------ pick work
        S_IDLE: begin
          if (take_msg) begin
            st_tasks <= st_tasks + 1; st_busy <= st_busy + 1;
            case (ej_f.kind)
              M_LINK: begin ra <= ej_f.p0; rb <= ej_f.p1; state <= S_LINK; end
              M_SPAWN: begin
                if (xown(ej_f.p0, ej_f.p1)) begin tp = 1'b1; tpr = TR_CROSS; tpp = lowown(ej_f.p0, ej_f.p1); end
                else begin sp_ref <= plab(ej_f.p0); sp_own <= pown(ej_f.p0); ex_x <= ej_f.p1; state <= S_EXPH; end
              end
              default: begin   // M_NODE: re-home the travelling node, then link it with its partner
                logic [SB-1:0] s;
                if (xown(ej_f.p0, ej_f.p3)) begin tp = 1'b1; tpr = TR_CROSS; tpp = lowown(ej_f.p0, ej_f.p3); end
                else begin
                  s = nstack[SB'(ntop - 1)];
                  ntop <= ntop - 1;
                  node_mem[s] <= MUT[10] ? {ej_f.p1, ej_f.p2} : {ej_f.p2, ej_f.p1};
                  nalloc[s] <= 1'b1; nown[s] <= pown(ej_f.p0);
                  ra <= withpay(ej_f.p0, here(s));
                  rb <= ej_f.p3;
                  state <= S_LINK;
                end
              end
            endcase
          end else if (take_q) begin
            logic [129:0] e;
            st_tasks <= st_tasks + 1; st_busy <= st_busy + 1;
            e = tq[QB'(qtop - 1)];
            qtop <= qtop - 1;
            if (e[129:128] == K_SPAWN) begin sp_ref <= plab(e[63:0]); sp_own <= pown(e[63:0]); sp_x <= e[127:64]; state <= S_SPAWN; end
            else begin ra <= e[63:0]; rb <= e[127:64]; state <= S_LINK; end
          end
        end

        // ------------------------------------------------------------------ link / redex dispatch
        S_LINK: begin
          logic [63:0] A, B, P, Q, old, a1, a2, b1, b2;
          logic [3:0] tP, tQ;
          logic [SB-1:0] sA, sP, sQ;
          logic rmt;
          if (!is_var(ra) && is_var(rb)) begin A = rb; B = ra; end else begin A = ra; B = rb; end
          sA = SB'(pslot(A));
          rmt = is_var(A) ? leaves(A) : ((is_node(A) && leaves(A)) || (is_node(B) && leaves(B)));
          if (xown(A, B) && !(fi[0] && rmt)) begin
            tp = 1'b1; tpr = TR_CROSS; tpp = lowown(A, B); state <= S_IDLE;
          end else if (is_var(A)) begin
            st_links <= st_links + 1;
            if (oob(A)) begin
              tp = 1'b1; tpr = TR_OOB; tpp = A; state <= S_IDLE;
            end else if (local_p(A)) begin
              logic forged;
              forged = vown[sA] != pown(A) && !MUT[16];
              if (forged) begin tp = 1'b1; tpr = TR_FORGED; tpp = A; end
              old = var_mem[sA];
              if (forged && !MUT[20]) begin
                state <= S_IDLE;
              end else if (ptag(old) == T_NONE) begin
                var_mem[sA] <= B;
                state <= S_IDLE;
              end else begin
                var_mem[sA] <= 64'd0; vown[sA] <= OWN_FREE;
                vstack[vtop[SB-1:0]] <= sA;
                vtop <= vtop + 1;
                ra <= old; rb <= B;            // continue linking old ~ B
                if (MUT[11]) state <= S_IDLE;
              end
            end else begin
              if (can_send) begin snd = 1'b1; sf = '{M_LINK, px(A), py(A), 64'd0, 64'd0, B, A}; end
              else begin qp = 1'b1; qe = {K_LINK, B, A}; end
              state <= S_IDLE;
            end
          end else begin
            // both principal: order the pair (bigger tag first)
            if (ptag(A) < ptag(B) || (ptag(A) == ptag(B) && plab(A) < plab(B))) begin P = B; Q = A; end
            else begin P = A; Q = B; end
            tP = ptag(P); tQ = ptag(Q);
            sP = SB'(pslot(P)); sQ = SB'(pslot(Q));
            a1 = node_mem[sP][63:0]; a2 = node_mem[sP][127:64];
            b1 = node_mem[sQ][63:0]; b2 = node_mem[sQ][127:64];
            state <= S_IDLE;
            if (tP <= T_NUM) begin
              // nullary ~ nullary
              st_inter <= st_inter + 1;
              if (tQ == T_REF && tP != T_ERA) begin sp_ref <= plab(Q); sp_own <= pown(Q); sp_x <= P; state <= S_SPAWN; end
            end else if (tQ <= T_NUM) begin
              // binary node P ~ nullary Q
              if (tQ == T_REF && (tP != T_DUP || MUT[13])) begin
                st_inter <= st_inter + 1;
                sp_ref <= plab(Q); sp_own <= pown(Q); sp_x <= P; state <= S_SPAWN;
              end else if (oob(P)) begin
                tp = 1'b1; tpr = TR_OOB; tpp = P;
              end else if (!local_p(P)) begin
                if (can_send) begin snd = 1'b1; sf = '{M_LINK, px(P), py(P), 64'd0, 64'd0, Q, P}; end
                else begin qp = 1'b1; qe = {K_LINK, Q, P}; end
              end else if (nown[sP] != pown(P) && !MUT[21]) begin
                tp = 1'b1; tpr = TR_FORGED; tpp = P;
              end else if (tP == T_SWI && tQ == T_NUM && pval(Q) != 0 && ntop == 0) begin
                qp = 1'b1; qe = {K_LINK, Q, P}; st_retry <= st_retry + 1;
              end else begin
                st_inter <= st_inter + 1;
                if (tQ == T_ERA || tQ == T_REF || tP == T_CON || tP == T_DUP) begin
                  // erase / copy: both aux ports receive Q
                  nfc = 2'd1; nf0 = sP; nalloc[sP] <= 1'b0; nown[sP] <= OWN_FREE;
                  pa[1] <= a2; pbv[1] <= (MUT[0] ? a1 : Q);
                  ra <= a1; rb <= Q; pidx <= 3'd1; state <= MUT[12] && tQ == T_ERA ? S_LINK : S_PUSH;
                end else if (tP == T_OPR) begin
                  logic [3:0] op; logic s;
                  op = P[47:44]; s = P[48];
                  if (ptag(a1) == T_NUM) begin
                    logic [31:0] r;
                    r = s ? alu(op, pval(a1), pval(Q)) : alu(op, pval(Q), pval(a1));
                    if (MUT[8] && op == 4'd7) r = s ? alu(4'd9, pval(a1), pval(Q)) : alu(4'd9, pval(Q), pval(a1));
                    if (MUT[1]) r = alu(op, pval(a1), pval(Q));
                    nfc = 2'd1; nf0 = sP; nalloc[sP] <= 1'b0; nown[sP] <= OWN_FREE;
                    ra <= a2; rb <= mkp(T_NUM, 16'd0, r); state <= S_LINK;
                  end else begin
                    node_mem[sP] <= {a2, Q};          // reuse the slot for the flipped operator
                    ra <= a1; rb <= mkpo(T_OPR, {11'd0, MUT[2] ? s : ~s, op}, pown(P), here(sP)); state <= S_LINK;
                  end
                end else begin  // SWI ~ NUM
                  if (pval(Q) == 0) begin
                    node_mem[sP] <= MUT[9] ? {a2, 64'h3000_0000_0000_0000} : {64'h3000_0000_0000_0000, a2};  // (a2 *)
                    ra <= a1; rb <= mkpo(T_CON, 16'd0, pown(P), here(sP)); state <= S_LINK;
                  end else begin
                    logic [SB-1:0] c2;
                    c2 = nstack[SB'(ntop - 1)];
                    ntop <= ntop - 1;
                    node_mem[sP] <= {a2, mkp(T_NUM, 16'd0, pval(Q) - (MUT[3] ? 32'd0 : 32'd1))};  // (#n-1 a2)
                    node_mem[c2] <= {mkpo(T_CON, 16'd0, pown(P), here(sP)), 64'h3000_0000_0000_0000}; // (* c1)
                    nalloc[c2] <= 1'b1; nown[c2] <= pown(P);
                    ra <= a1; rb <= mkpo(T_CON, 16'd0, pown(P), here(c2)); state <= S_LINK;
                  end
                end
              end
            end else begin
              // binary ~ binary
              logic lP, lQ, anni;
              lP = local_p(P); lQ = local_p(Q);
              anni = (tP == tQ) && (plab(P) == plab(Q)) && (tP == T_CON || tP == T_DUP);
              if (MUT[4]) anni = (tP == tQ) && (tP == T_CON || tP == T_DUP);
              if (oob(P)) begin
                tp = 1'b1; tpr = TR_OOB; tpp = P;
              end else if (oob(Q)) begin
                tp = 1'b1; tpr = TR_OOB; tpp = Q;
              end else if (lP && nown[sP] != pown(P) && !MUT[21]) begin
                tp = 1'b1; tpr = TR_FORGED; tpp = P;
              end else if (lQ && nown[sQ] != pown(Q) && !MUT[21]) begin
                tp = 1'b1; tpr = TR_FORGED; tpp = Q;
              end else if (lP && lQ) begin
                if (!anni && (ntop < 2 || vtop < 4)) begin
                  qp = 1'b1; qe = {K_LINK, Q, P}; st_retry <= st_retry + 1;
                end else if (anni) begin
                  st_inter <= st_inter + 1;
                  nfc = 2'd2; nf0 = sP; nf1 = sQ; nalloc[sP] <= 1'b0; nalloc[sQ] <= 1'b0;
                  nown[sP] <= OWN_FREE; nown[sQ] <= OWN_FREE;
                  pa[1] <= a2; pbv[1] <= b2;
                  ra <= a1; rb <= (MUT[5] ? b2 : b1); pidx <= 3'd1; state <= S_PUSH;
                end else begin
                  logic [SB-1:0] n1, n3, v0, v1, v2, v3;
                  logic [63:0] x11, x12, x21, x22;
                  st_inter <= st_inter + 1;
                  n1 = nstack[SB'(ntop - 1)]; n3 = nstack[SB'(ntop - 2)];
                  v0 = vstack[SB'(vtop - 1)]; v1 = vstack[SB'(vtop - 2)];
                  v2 = vstack[SB'(vtop - 3)]; v3 = vstack[SB'(vtop - 4)];
                  ntop <= ntop - 2; vtop <= vtop - 4;
                  x11 = mkpo(T_VAR, 16'd0, pown(P), here(v0)); x12 = mkpo(T_VAR, 16'd0, pown(P), here(v1));
                  x21 = mkpo(T_VAR, 16'd0, pown(P), here(v2)); x22 = mkpo(T_VAR, 16'd0, pown(P), here(MUT[14] ? v2 : v3));
                  vown[v0] <= pown(P); vown[v1] <= pown(P); vown[v2] <= pown(P); vown[v3] <= pown(P);
                  nown[n1] <= pown(P); nown[n3] <= pown(P); nown[sQ] <= pown(P);
                  node_mem[sP] <= {x12, x11};               // copy 1 of Q's kind
                  node_mem[n1] <= {x22, x21};               // copy 2 of Q's kind
                  node_mem[sQ] <= {x21, x11};               // copy 1 of P's kind
                  node_mem[n3] <= MUT[6] ? {x12, x22} : {x22, x12};   // copy 2 of P's kind
                  nalloc[n1] <= 1'b1; nalloc[n3] <= 1'b1;
                  pa[1] <= a2; pbv[1] <= withpay(Q, here(n1));
                  pa[2] <= b1; pbv[2] <= withpay(P, here(sQ));
                  pa[3] <= b2; pbv[3] <= withpay(P, here(n3));
                  ra <= a1; rb <= withpay(Q, here(sP)); pidx <= 3'd3; state <= S_PUSH;
                end
              end else if (lP || lQ) begin
                logic [63:0] L, R, l1, l2;
                L = lP ? P : Q; R = lP ? Q : P;
                l1 = lP ? a1 : b1; l2 = lP ? a2 : b2;
                if (can_send) begin
                  // migrate the local node to the partner's cell (MSG NODE)
                  snd = 1'b1; sf = '{M_NODE, px(R), py(R), R, l2, l1, L};
                  nfc = 2'd1; nf0 = SB'(pslot(L)); nalloc[SB'(pslot(L))] <= 1'b0; nown[SB'(pslot(L))] <= OWN_FREE;
                end else begin qp = 1'b1; qe = {K_LINK, Q, P}; st_retry <= st_retry + 1; end
              end else begin
                if (can_send) begin snd = 1'b1; sf = '{M_LINK, px(P), py(P), 64'd0, 64'd0, Q, P}; end
                else begin qp = 1'b1; qe = {K_LINK, Q, P}; end
              end
            end
          end
        end

        // ------------------------------------------------------------------ push extra links, then continue with (ra, rb)
        S_PUSH: begin
          qp = 1'b1; qe = {K_LINK, pbv[pidx[1:0]], pa[pidx[1:0]]};
          if (pidx == 3'd1) state <= S_LINK;
          pidx <= pidx - 1;
        end

        // ------------------------------------------------------------------ choose where a REF expands
        S_SPAWN: begin
          // give the expansion to a hungry neighbour if there is one, otherwise expand here
          hrot <= hrot + 2'd1;
          if (!hv_found || !can_send || MUT[7]) begin
            ex_x <= sp_x; state <= S_EXPH;
          end else begin
            snd = 1'b1; sf = '{M_SPAWN, dir_x(hv_dir), dir_y(hv_dir), 64'd0, 64'd0, sp_x, mkpo(T_REF, sp_ref, sp_own, 32'd0)};
            state <= S_IDLE;
          end
        end

        // ------------------------------------------------------------------ EXPAND: header
        S_EXPH: begin
          logic [15:0] base; logic [127:0] hdr; logic [7:0] nn, nv, nr;
          base = dirm[sp_ref[$clog2(DIRSZ)-1:0]];
          hdr = rom[base[$clog2(ROMSZ)-1:0]];
          nn = hdr[71:64]; nv = hdr[79:72]; nr = hdr[87:80];
          if ((SB+1)'(nn) <= ntop && (SB+1)'(nv) <= vtop && (32'(qtop) + 32'(nr) + 1) < QDEPTH) begin
            ex_base <= base + 1; ex_nn <= nn; ex_nv <= nv; ex_nr <= nr; ex_root <= hdr[63:0];
            nb <= ntop; vb <= vtop; ex_own <= sp_own;
            ntop <= ntop - (SB+1)'(nn); vtop <= vtop - (SB+1)'(nv);
            ex_i <= 8'd0;
            state <= (nn != 0 || nv != 0) ? S_EXPN : S_EXPR;
          end else if (NT > 1) begin
            // not enough room here: forward the SPAWN to a neighbour
            logic [2:0] t;
            t = (rr == 3'd0) ? 3'd1 : rr;
            rr <= (t == 3'(NT - 1)) ? 3'd0 : t + 1;
            st_retry <= st_retry + 1;
            if (can_send) begin snd = 1'b1; sf = '{M_SPAWN, tx[t], ty[t], 64'd0, 64'd0, ex_x, mkpo(T_REF, sp_ref, sp_own, 32'd0)}; end
            else begin qp = 1'b1; qe = {K_SPAWN, ex_x, mkpo(T_REF, sp_ref, sp_own, 32'd0)}; end
            state <= S_IDLE;
          end else begin
            err <= 4'd2; state <= S_HALT;    // out of memory on a 1x1 fabric
          end
        end

        S_EXPN: begin
          logic [127:0] e; logic [SB-1:0] s;
          // one node write and one var owner-tag write per cycle: max(nn, nv) cycles
          e = rom[$clog2(ROMSZ)'(ex_base + 16'(ex_i))];
          s = nstack[SB'(nb - 1 - (SB+1)'(ex_i))];
          if (ex_i < ex_nn) begin
            node_mem[s] <= {tr(e[127:64]), tr(e[63:0])};
            nalloc[s] <= 1'b1; nown[s] <= MUT[19] ? 4'd0 : ex_own;
          end
          if (ex_i < ex_nv) vown[vstack[SB'(vb - 1 - (SB+1)'(ex_i))]] <= MUT[19] ? 4'd0 : ex_own;
          ex_i <= ex_i + 1;
          if (ex_i + 1 >= ex_nn && ex_i + 1 >= ex_nv) begin ex_i <= 8'd0; state <= S_EXPR; end
        end

        S_EXPR: begin
          if (ex_i < ex_nr) begin
            logic [127:0] e;
            e = rom[$clog2(ROMSZ)'(ex_base + 16'(ex_nn) + 16'(ex_i))];
            qp = 1'b1; qe = {K_LINK, tr(e[127:64]), tr(e[63:0])};
            ex_i <= ex_i + 1;
          end else begin
            ra <= tr(ex_root); rb <= ex_x; state <= S_LINK;
          end
        end

        default: ;   // S_HALT
      endcase

      // ---- apply side effects ----
      if (tp) begin
        st_traps <= st_traps + 1;
        tr_mask[(32'(tpr) - 1) * 16 + 32'(pown(tpp))] <= 1'b1;
        if (st_traps == 0) begin tr_reason <= tpr; tr_owner <= pown(tpp); tr_addr <= pval(tpp); end
      end
      if (qp) begin
        if (qtop == (QB+1)'(QDEPTH)) begin err <= 4'd1; state <= S_HALT; end
        else begin
          tq[QB'(qtop)] <= qe;
          qtop <= qtop + 1;
          if (32'(qtop) + 1 > st_maxq) st_maxq <= 32'(qtop) + 1;
        end
      end
      if (nfc != 0) begin
        nstack[ntop[SB-1:0]] <= nf0;
        if (nfc == 2'd2) nstack[SB'(ntop + 1)] <= nf1;
        ntop <= ntop + (SB+1)'(nfc);
      end
      begin
        logic pop;
        pop = l_pop && ob_cnt != 0;
        if (snd) begin
          ob[ob_hd + OB'(ob_cnt)] <= sf;
          case (sf.kind) M_LINK: st_msg0 <= st_msg0 + 1; M_NODE: st_msg1 <= st_msg1 + 1; default: st_msg2 <= st_msg2 + 1; endcase
        end
        if (pop) ob_hd <= ob_hd + 1'b1;
        ob_cnt <= ob_cnt + (OB+1)'(snd) - (OB+1)'(pop);
      end
    end
  end

  // ---------------- dump (testbench) ----------------
  always @(posedge clk) begin
    if (dump) begin
      int fd;
      $writememh($sformatf("%s/out_node_%0d_%0d.hex", outdir, X, Y), node_mem);
      $writememh($sformatf("%s/out_nalloc_%0d_%0d.hex", outdir, X, Y), nalloc);
      $writememh($sformatf("%s/out_var_%0d_%0d.hex", outdir, X, Y), var_mem);
      $writememh($sformatf("%s/out_nown_%0d_%0d.hex", outdir, X, Y), nown);
      fd = $fopen($sformatf("%s/out_stats_%0d_%0d.txt", outdir, X, Y), "w");
      $fwrite(fd, "cycles %0d\ninteractions %0d\nbusy %0d\ntasks %0d\nlinks %0d\nretry %0d\nmsg_link %0d\nmsg_node %0d\nmsg_spawn %0d\nmaxq %0d\nfree_nodes %0d\nfree_vars %0d\nerr %0d\npeak_nodes %0d\npeak_vars %0d\ntraps %0d\ntrap_reason %0d\ntrap_owner %0d\ntrap_addr %0d\ntrap_mask %0d\n",
              cyc, st_inter, st_busy, st_tasks, st_links, st_retry, st_msg0, st_msg1, st_msg2, st_maxq, ntop, vtop, err, SLOTS - st_minfn, SLOTS - st_minfv, st_traps, tr_reason, tr_owner, tr_addr, tr_mask);
      $fclose(fd);
    end
  end
endmodule
