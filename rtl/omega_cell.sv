// TACHYON-Omega active memory cell (v2: SRAM-style storage).
//
// Storage is written so that synthesis infers 1R1W synchronous SRAM macros (one write statement and
// one registered read per array):
//   node RAM  SLOTS x 132 b  {owner[3:0], aux2, aux1}
//   var RAM   SLOTS x 68 b   {owner[3:0], substitution}
//   free node / free var stacks and the task stack: a K-entry register top cache over a 1R1W SRAM
//   (CSTACK macro), definition ROM and directory: synchronous 1R ROMs.
// Flip-flops: the per-slot `nalloc` valid bits (1 bit per node slot), the 64-entry expansion maps,
// the stack caches, the router FIFOs / outbox and the engine registers.
//
// There is no program counter and no instruction stream: the engine only reacts to a task on its
// own stack or to a message from a neighbour.  SPEC.md section 5 has the state machine and the
// cycle costs, section 3 the rule table, section 12 the owner-capability checks.
// Register-cached LIFO update:
// pops and pushes act on the cache; a refill that arrives goes below everything; a spill moves the
// bottom entry into the SRAM part.  One SRAM write (spill) and one registered SRAM read per cycle.
`define CSTACK(C, CNT, SP, PEND, MEM, RD, K, HI, LO, POPN, PUSHN, PD, NPUSH, D, WD, AB, nn_) \
      begin \
        cs_after = 5'(CNT) - 5'(POPN) + 5'(PUSHN); \
        cs_spill = !PEND && cs_after > 5'(HI) && SP < (AB+1)'(D); \
        cs_fill  = !cs_spill && (32'(cs_after) + 32'(PEND)) < LO && SP != 0; \
        for (int i_ = 0; i_ < K; i_++) nn_[i_] = C[i_]; \
        cs_m = 5'(CNT) - 5'(POPN); \
        for (int j_ = 0; j_ < NPUSH; j_++) if (j_ < 32'(PUSHN)) begin nn_[cs_m[3:0]] = PD[j_]; cs_m = cs_m + 1; end \
        if (PEND) begin for (int i_ = K - 1; i_ > 0; i_--) nn_[i_] = nn_[i_ - 1]; nn_[0] = RD; cs_m = cs_m + 1; end \
        if (cs_spill) begin MEM[AB'(SP)] <= C[0]; for (int i_ = 0; i_ < K - 1; i_++) nn_[i_] = nn_[i_ + 1]; cs_m = cs_m - 1; end \
        for (int i_ = 0; i_ < K; i_++) C[i_] <= nn_[i_]; \
        CNT <= cs_m[3:0]; \
        SP <= SP + (AB+1)'(cs_spill) - (AB+1)'(cs_fill); \
        PEND <= cs_fill; \
        RD <= MEM[AB'(SP - 1)]; \
      end

`include "omega_defs.svh"
`define TR(P) tr(P, ex_own, vmap[XB'(pval(P))], nmap[XB'(pval(P))])
module omega_cell #(
  parameter int X = 0, parameter int Y = 0, parameter int W = 1, parameter int H = 1,
  parameter int SLOTS = 1024, parameter int QDEPTH = 1024,
  parameter int ROMSZ = 4096, parameter int DIRSZ = 256, parameter int DEPTH = 4,
  parameter int XMAP = 64,                  // max nodes / vars per definition (expansion maps)
  parameter logic [255:0] MUT = '0          // mutation-testing knobs (0 = correct design)
) (
  input  logic        clk, rst,
  input  logic [31:0] seed,
  input  logic [7:0]  jitter, stall, pmsg,
  input  logic [7:0]  fi,                  // fault injection: bit 0 = sender skips the cross-owner check
  input  logic [3:0]  in_v,
  input  flit_t [3:0] in_f,
  output logic [3:0]  in_rdy,
  output logic [3:0]  out_v,
  output flit_t [3:0] out_f,
  input  logic [3:0]  out_rdy,
  output logic        idle,
  output logic        hungry,              // to neighbours: no local work (demand-driven spawn)
  input  logic [3:0]  nbr_hungry,          // from neighbours N, E, S, W
  output logic        ready,               // initialisation finished
  output logic [3:0]  err,
  input  logic        dump,
  // loader port for the replicated definition ROM / directory (simulation preloads them with $readmemh)
  input  logic        cfg_we,
  input  logic        cfg_dir,             // 0 = ROM entry, 1 = directory entry
  input  logic [15:0] cfg_a,
  input  logic [127:0] cfg_d,
  output logic [31:0] st_inter
);
  `include "omega_funcs.svh"
  localparam int SB = $clog2(SLOTS);
  localparam int QB = $clog2(QDEPTH);
  localparam int OB = $clog2(DEPTH);
  localparam int RB = $clog2(ROMSZ);
  localparam int DB = $clog2(DIRSZ);
  localparam int XB = $clog2(XMAP);
  localparam logic [63:0] ERA_P = 64'h3000_0000_0000_0000;

  typedef enum logic [4:0] {S_INIT, S_IDLE, S_LINK, S_LVAR, S_RDQ, S_RULE, S_PUSH, S_SPAWN,
                            S_EX0, S_EX1, S_EX2, S_EXA, S_EXN, S_EXR, S_HALT} st_t;
  st_t state;
  typedef enum logic [1:0] {R_NA, R_BB, R_MIG} rk_t;     // rule kinds read in S_RULE
  rk_t rkind;

  // Memories: every array below has exactly one write statement and one registered read (end of the
  // sequential block), so synthesis infers 1R1W synchronous SRAMs (ROM/dir: 1R).
  logic [131:0] node_mem [SLOTS];       // {owner, aux2, aux1}
  logic [67:0]  var_mem  [SLOTS];       // {owner, substitution}
  logic [127:0] rom  [ROMSZ];           // definition templates {b, a}
  logic [15:0]  dirm [DIRSZ];
  logic [SB-1:0] nstk [SLOTS];          // free node stack (SRAM part)
  logic [SB-1:0] vstk [SLOTS];          // free var stack (SRAM part)
  logic [129:0] tqm  [QDEPTH];          // task stack (SRAM part) {kind, b, a}
  // synchronous read data
  logic [131:0] n_rd;  logic [67:0] v_rd;  logic [127:0] r_rd;  logic [15:0] d_rd;
  logic [SB-1:0] nstk_rd, vstk_rd;  logic [129:0] tqm_rd;
  logic [SB-1:0] n_ra, v_ra;  logic [RB-1:0] r_ra;  logic [DB-1:0] d_ra;
  // stack top caches (registers): c[0] bottom .. c[cnt-1] top; sp = entries in the SRAM part
  localparam int NK = 8, VK = 8, QK = 4;
  logic [NK-1:0][SB-1:0] nc;  logic [3:0] ncnt;  logic [SB:0] nsp;  logic npend;
  logic [VK-1:0][SB-1:0] vc;  logic [3:0] vcnt;  logic [SB:0] vsp;  logic vpend;
  logic [QK-1:0][129:0]  qc;  logic [3:0] qcnt;  logic [QB:0] qsp;  logic qpend;
  // ---------------- storage ----------------
  logic [SLOTS-1:0] nalloc;             // valid bit per node slot (flip-flops; readback + free check)
  logic [SLOTS-1:0] valloc;             // initial var allocation (image only, used while building the free stack)
  logic [15:0]  qinit [1];
`ifndef SYNTHESIS
  logic na_init [SLOTS], va_init [SLOTS], na_out [SLOTS];
  string imgdir, outdir;
  initial begin
    if (!$value$plusargs("img=%s", imgdir)) imgdir = "build/img";
    if (!$value$plusargs("out=%s", outdir)) outdir = imgdir;
    $readmemh($sformatf("%s/nalloc_%0d_%0d.hex", imgdir, X, Y), na_init);
    $readmemh($sformatf("%s/valloc_%0d_%0d.hex", imgdir, X, Y), va_init);
    for (int i = 0; i < SLOTS; i++) begin nalloc[i] = na_init[i]; valloc[i] = va_init[i]; end
    $readmemh($sformatf("%s/qcount_%0d_%0d.hex", imgdir, X, Y), qinit);
    $readmemh($sformatf("%s/node_%0d_%0d.hex", imgdir, X, Y), node_mem);
    $readmemh($sformatf("%s/var_%0d_%0d.hex", imgdir, X, Y), var_mem);
    $readmemh($sformatf("%s/queue_%0d_%0d.hex", imgdir, X, Y), tqm);
    $readmemh($sformatf("%s/rom.hex", imgdir), rom);
    $readmemh($sformatf("%s/dir.hex", imgdir), dirm);
  end
`else
  initial qinit[0] = '0;
`endif

  logic [1:0][SB-1:0] nf_top;
  logic [3:0][SB-1:0] vf_top;
  logic [129:0]   tq_top;
  logic [3:0]     nf_av, nf_room, vf_av, vf_room, tq_av, tq_room;
  logic [SB+1:0]  nf_tot, vf_tot;
  logic [QB+1:0]  tq_tot;
  always_comb begin
    for (int i = 0; i < 2; i++) nf_top[i] = (32'(ncnt) > i) ? nc[32'(ncnt) - 1 - i] : '0;
    for (int i = 0; i < 4; i++) vf_top[i] = (32'(vcnt) > i) ? vc[32'(vcnt) - 1 - i] : '0;
    tq_top = (qcnt != 0) ? qc[qcnt - 1] : '0;
    nf_av = ncnt; vf_av = vcnt; tq_av = qcnt;
    nf_room = 4'(NK) - ncnt - 4'(npend); vf_room = 4'(VK) - vcnt - 4'(vpend); tq_room = 4'(QK) - qcnt - 4'(qpend);
    nf_tot = (SB+2)'(ncnt) + (SB+2)'(nsp) + (SB+2)'(npend);
    vf_tot = (SB+2)'(vcnt) + (SB+2)'(vsp) + (SB+2)'(vpend);
    tq_tot = (QB+2)'(qcnt) + (QB+2)'(qsp) + (QB+2)'(qpend);
  end

  flit_t [DEPTH-1:0] ob;                // outbox (router local input)
  logic [OB:0]  ob_cnt;
  logic [OB-1:0] ob_hd;

  // ---------------- router ----------------
  logic  l_pop, ej_v, ej_pop, rbusy;
  flit_t ej_f, ob_head;
  assign ob_head = ob[ob_hd];
  omega_router #(.X(X), .Y(Y), .DEPTH(DEPTH)) u_rt (
    .clk, .rst, .seed, .jitter, .in_v, .in_f, .in_rdy, .out_v, .out_f, .out_rdy,
    .l_v(ob_cnt != 0), .l_f(ob_head), .l_pop, .ej_v, .ej_f, .ej_pop, .busy(rbusy));

  // spawn targets: index 0 = self, then existing neighbours in E S W N order
  localparam int HAS_E = (X < W - 1) ? 1 : 0, HAS_S = (Y < H - 1) ? 1 : 0;
  localparam int HAS_W = (X > 0) ? 1 : 0,     HAS_N = (Y > 0) ? 1 : 0;
  localparam int NT = 1 + HAS_E + HAS_S + HAS_W + HAS_N;
  logic [4:0][3:0] tx, ty;
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
    dir_x = (d == 2'd1) ? 4'(X + 1) : (d == 2'd3) ? 4'(X - 1) : 4'(X);
  endfunction
  function automatic logic [3:0] dir_y(input logic [1:0] d);
    dir_y = (d == 2'd0) ? 4'(Y - 1) : (d == 2'd2) ? 4'(Y + 1) : 4'(Y);
  endfunction

  // ---------------- engine registers ----------------
  logic [63:0] ra, rb;                  // current link
  logic [63:0] rP, rQ;                  // ordered redex being read / executed
  logic [127:0] pdat;                   // first node read (P) for two-node rules
  logic [SB-1:0] nhold;                 // node RAM read address held while waiting
  logic [3:0][63:0] pa, pbv;            // extra links produced by a rule, pushed in S_PUSH
  logic [2:0]  pcnt;
  logic [2:0][SB-1:0] wq_a;             // queued node writes (commutation / SWI)
  logic [2:0][131:0]  wq_d;
  logic [1:0]    wq_n;
  logic [2:0][SB-1:0] vq_a;             // queued var owner-tag writes (commutation)
  logic [1:0]    vq_n;
  logic [3:0]    vq_o;
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
  logic [XMAP-1:0][SB-1:0] nmap;        // expansion: local index -> allocated slot
  logic [XMAP-1:0][SB-1:0] vmap;
  logic [31:0] erng;
  logic [SB:0] init_i;
  logic [SB+1:0] st_minfn, st_minfv;
  logic [31:0] cyc, st_busy, st_retry, st_msg0, st_msg1, st_msg2, st_maxq, st_links, st_tasks;

  function automatic logic local_p(input logic [63:0] p);
    local_p = px(p) == 4'(X) && py(p) == 4'(Y);
  endfunction
  function automatic logic [31:0] here(input logic [SB-1:0] s);
    here = mkaddr(4'(X), 4'(Y), 12'(s));
  endfunction
  // T3: pointer outside the fabric (or malformed address bits)
  function automatic logic oob(input logic [63:0] p);
    oob = !MUT[18] && (32'(px(p)) >= W || 32'(py(p)) >= H || 32'(pslot(p)) >= SLOTS || p[31:24] != 8'd0 || p[15:12] != 4'd0);
  endfunction
  function automatic logic leaves(input logic [63:0] p);   // pointer is remote or out of bounds
    leaves = oob(p) || !local_p(p);
  endfunction
  function automatic logic [63:0] lowown(input logic [63:0] a, input logic [63:0] b);  // CROSS trap blames the lower owner id
    lowown = (pown(a) < pown(b)) ? a : b;
  endfunction
  // T1: two capabilities of different owners meet
  function automatic logic xown(input logic [63:0] a, input logic [63:0] b);
    xown = !MUT[17] && is_cap(a) && is_cap(b) && pown(a) != pown(b);
  endfunction
  // T2 for a node slot: valid and tagged with the pointer's owner (nalloc read by the caller)
  function automatic logic nforged(input logic valid, input logic [63:0] p, input logic [131:0] w);
    nforged = !MUT[21] && (!valid || w[131:128] != pown(p));
  endfunction

  // ---------------- link decode (combinational, from ra/rb) ----------------
  logic [63:0] A, B, dP, dQ;
  logic        dvar, dlP, dlQ;
  always_comb begin
    if (!is_var(ra) && is_var(rb)) begin A = rb; B = ra; end else begin A = ra; B = rb; end
    dvar = is_var(A);
    if (ptag(A) < ptag(B) || (ptag(A) == ptag(B) && plab(A) < plab(B))) begin dP = B; dQ = A; end
    else begin dP = A; dQ = B; end
    dlP = is_node(dP) && !oob(dP) && local_p(dP);
    dlQ = is_node(dQ) && !oob(dQ) && local_p(dQ);
  end

  // slots a rule will pop from the stack caches (it waits until the caches hold them; a rule whose
  // slots are not free at all is re-queued instead, as in v1)
  int rneed_n, rneed_v;
  always_comb begin
    logic anni_;
    anni_ = (ptag(rP) == ptag(rQ)) && (plab(rP) == plab(rQ)) && (ptag(rP) == T_CON || ptag(rP) == T_DUP);
    if (MUT[4]) anni_ = (ptag(rP) == ptag(rQ)) && (ptag(rP) == T_CON || ptag(rP) == T_DUP);
    rneed_n = 0; rneed_v = 0;
    if (rkind == R_NA && ptag(rP) == T_SWI && ptag(rQ) == T_NUM && pval(rQ) != 0 && nf_tot != 0) rneed_n = 1;
    if (rkind == R_BB && !anni_ && nf_tot >= 2 && vf_tot >= 4) begin rneed_n = 2; rneed_v = 4; end
  end

  // ---------------- source selection (combinational, also drives the ejection pop) ----------------
  logic can_send, msg_ok, q_ok, stall_now, pick_msg, take_msg, take_q;
  always_comb begin
    can_send  = ob_cnt < (OB+1)'(DEPTH);
    msg_ok    = ej_v && !(ej_f.kind == M_NODE && nf_av == 0);
    q_ok      = tq_av != 0;
    stall_now = (stall != 0) && (erng[7:0] < stall);
    pick_msg  = msg_ok && (!q_ok || !can_send || (erng[15:8] < pmsg));
    take_msg  = (state == S_IDLE) && !stall_now && pick_msg;
    take_q    = (state == S_IDLE) && !stall_now && q_ok && !pick_msg;
    ej_pop    = take_msg;
    idle      = (state == S_IDLE) && (tq_tot == 0) && !ej_v && (ob_cnt == 0) && (!rbusy || MUT[15]);
    ready     = state != S_INIT;
    hungry    = (state == S_IDLE) && (tq_tot == 0) && !ej_v;
  end

  // translation of a template port during EXPAND (stamps the expanding owner, relocates via the maps)
  // (nmap / vmap entries are looked up by the caller: functions may not read module arrays in Yosys)
  function automatic logic [63:0] tr(input logic [63:0] p, input logic [3:0] own,
                                     input logic [SB-1:0] vslot, input logic [SB-1:0] nslot);
    logic [3:0] t, o;
    t = ptag(p);
    o = MUT[19] ? 4'd0 : own;
    if (p[39]) tr = {p[63:44], o, 1'b0, p[38:0]};          // absolute (forged) pointer: no relocation
    else if (t == T_VAR) tr = mkpo(T_VAR, 16'd0, o, here(vslot));
    else if (t == T_CON || t == T_DUP || t == T_OPR || t == T_SWI) tr = withown(withpay(p, here(nslot)), o);
    else if (t == T_REF) tr = withown(p, o);
    else tr = p;
  endfunction

  // ---------------- RAM read addresses (held stable while a state waits) ----------------
  always_comb begin
    v_ra = SB'(pslot(A));
    n_ra = nhold;
    if (state == S_LINK) n_ra = dlP ? SB'(pslot(dP)) : SB'(pslot(dQ));
    else if (state == S_RDQ) n_ra = SB'(pslot(rQ));
    d_ra = DB'(sp_ref);
    r_ra = RB'(ex_base);
    case (state)
      S_EX1:  r_ra = RB'(d_rd);
      S_EX2:  r_ra = RB'(d_rd);
      S_EXA:  r_ra = RB'(ex_base);                              // first template node
      S_EXN:  r_ra = RB'(ex_base + 16'(ex_i) + 16'd1);           // prefetch the next entry
      S_EXR:  r_ra = RB'(ex_base + 16'(ex_nn) + 16'(ex_i) + ((tq_room != 0) ? 16'd1 : 16'd0));
      default: ;
    endcase
  end

  // Per-cycle temporaries of the sequential block (blocking-assigned first thing every cycle, so
  // synthesis keeps them combinational; declared here because Yosys mishandles packed-array locals).
  logic snd; flit_t sf;
  logic qp; logic [129:0] qe;
  logic tp; logic [1:0] tpr; logic [63:0] tpp;
  logic [2:0] nf_pop, nf_push, vf_pop, vf_push, tq_pop, tq_push;
  logic [1:0][SB-1:0] nf_pd; logic [0:0][SB-1:0] vf_pd;
  logic [0:0][129:0] tq_pd;
  logic n_we, v_we; logic [SB-1:0] n_wa, v_wa; logic [131:0] n_wd; logic [67:0] v_wd;
  logic [NK-1:0][SB-1:0] nc_n; logic [VK-1:0][SB-1:0] vc_n; logic [QK-1:0][129:0] qc_n;
  logic [4:0] cs_m, cs_after; logic cs_spill, cs_fill;

  always_ff @(posedge clk) begin
    if (rst) begin
      state <= S_INIT;
      init_i <= (SB+1)'(SLOTS);
      ob_cnt <= '0; ob_hd <= '0;
      err <= '0; rr <= '0; hrot <= 2'(X + Y);
      erng <= seed ^ (32'h85EBCA6B * (X * 16 + Y + 7)) ^ 32'h2;
      cyc <= '0; st_inter <= '0; st_busy <= '0; st_retry <= '0; st_msg0 <= '0; st_msg1 <= '0;
      st_msg2 <= '0; st_maxq <= '0; st_links <= '0; st_tasks <= '0;
      st_minfn <= '1; st_minfv <= '1;
      st_traps <= '0; tr_addr <= '0; tr_reason <= '0; tr_owner <= '0; tr_mask <= '0;
      wq_n <= '0; vq_n <= '0; pcnt <= '0;
      ncnt <= '0; nsp <= '0; npend <= 1'b0;
      vcnt <= '0; vsp <= '0; vpend <= 1'b0;
      qcnt <= '0; qsp <= (QB+1)'(qinit[0]); qpend <= 1'b0;
    end else begin
      // per-cycle temporaries: module-scope variables assigned with '=' at the top of this block
      snd = 1'b0; sf = '0; qp = 1'b0; qe = '0;
      tp = 1'b0; tpr = '0; tpp = '0;
      nf_pop = '0; nf_push = '0; nf_pd[0] = '0; nf_pd[1] = '0;
      vf_pop = '0; vf_push = '0; vf_pd[0] = '0;
      tq_pop = '0;
      n_we = 1'b0; n_wa = '0; n_wd = '0;
      v_we = 1'b0; v_wa = '0; v_wd = '0;
      erng <= xorshift(erng);
      if (state != S_INIT && nf_tot < st_minfn) st_minfn <= nf_tot;
      if (state != S_INIT && vf_tot < st_minfv) st_minfv <= vf_tot;
      if (state != S_INIT) cyc <= cyc + 1;
      if (state != S_IDLE && state != S_INIT && state != S_HALT) st_busy <= st_busy + 1;

      case (state)
        // ------------------------------------------------------------------ init: build free stacks
        S_INIT: begin
          logic [SB-1:0] i;
          i = SB'(init_i - 1);
          if (nf_room != 0 && vf_room != 0) begin
            if (!nalloc[i]) begin nf_push = 3'd1; nf_pd[0] = i; end
            if (!valloc[i]) begin vf_push = 3'd1; vf_pd[0] = i; end
            init_i <= init_i - 1;
            if (init_i == 1) state <= S_IDLE;
          end
        end

        // ------------------------------------------------------------------ pick work
        S_IDLE: begin
          if (take_msg) begin
            st_tasks <= st_tasks + 1; st_busy <= st_busy + 1;
            case (ej_f.kind)
              M_LINK: begin ra <= ej_f.p0; rb <= ej_f.p1; state <= S_LINK; end
              M_SPAWN: begin
                if (xown(ej_f.p0, ej_f.p1)) begin tp = 1'b1; tpr = TR_CROSS; tpp = lowown(ej_f.p0, ej_f.p1); end
                else begin sp_ref <= plab(ej_f.p0); sp_own <= pown(ej_f.p0); ex_x <= ej_f.p1; state <= S_EX0; end
              end
              default: begin   // M_NODE: re-home the travelling node, then link it with its partner
                logic [SB-1:0] s;
                if (xown(ej_f.p0, ej_f.p3)) begin tp = 1'b1; tpr = TR_CROSS; tpp = lowown(ej_f.p0, ej_f.p3); end
                else begin
                  s = nf_top[0]; nf_pop = 3'd1;
                  n_we = 1'b1; n_wa = s;
                  n_wd = {pown(ej_f.p0), MUT[10] ? {ej_f.p1, ej_f.p2} : {ej_f.p2, ej_f.p1}};
                  nalloc[s] <= 1'b1;
                  ra <= withpay(ej_f.p0, here(s));
                  rb <= ej_f.p3;
                  state <= S_LINK;
                end
              end
            endcase
          end else if (take_q) begin
            logic [129:0] e;
            st_tasks <= st_tasks + 1; st_busy <= st_busy + 1;
            e = tq_top; tq_pop = 3'd1;
            if (e[129:128] == K_SPAWN) begin sp_ref <= plab(e[63:0]); sp_own <= pown(e[63:0]); sp_x <= e[127:64]; state <= S_SPAWN; end
            else begin ra <= e[63:0]; rb <= e[127:64]; state <= S_LINK; end
          end
        end

        // ------------------------------------------------------------------ link / redex dispatch
        S_LINK: if (tq_room != 0) begin
          logic rmt;
          logic [3:0] tP, tQ;
          rmt = dvar ? leaves(A) : ((is_node(A) && leaves(A)) || (is_node(B) && leaves(B)));
          tP = ptag(dP); tQ = ptag(dQ);
          state <= S_IDLE;
          if (xown(A, B) && !(fi[0] && rmt)) begin
            tp = 1'b1; tpr = TR_CROSS; tpp = lowown(A, B);
          end else if (dvar) begin
            st_links <= st_links + 1;
            if (oob(A)) begin
              tp = 1'b1; tpr = TR_OOB; tpp = A;
            end else if (local_p(A)) begin
              state <= S_LVAR;                 // var RAM read issued (v_ra = slot(A))
            end else begin
              if (can_send) begin snd = 1'b1; sf = {M_LINK, px(A), py(A), 64'd0, 64'd0, B, A}; end
              else begin qp = 1'b1; qe = {K_LINK, B, A}; end
            end
          end else begin
            rP <= dP; rQ <= dQ;
            if (tP <= T_NUM) begin
              // nullary ~ nullary
              st_inter <= st_inter + 1;
              if (tQ == T_REF && tP != T_ERA) begin sp_ref <= plab(dQ); sp_own <= pown(dQ); sp_x <= dP; state <= S_SPAWN; end
            end else if (tQ <= T_NUM) begin
              // binary node P ~ nullary Q
              if (tQ == T_REF && (tP != T_DUP || MUT[13])) begin
                st_inter <= st_inter + 1;
                sp_ref <= plab(dQ); sp_own <= pown(dQ); sp_x <= dP; state <= S_SPAWN;
              end else if (oob(dP)) begin
                tp = 1'b1; tpr = TR_OOB; tpp = dP;
              end else if (!local_p(dP)) begin
                if (can_send) begin snd = 1'b1; sf = {M_LINK, px(dP), py(dP), 64'd0, 64'd0, dQ, dP}; end
                else begin qp = 1'b1; qe = {K_LINK, dQ, dP}; end
              end else begin
                nhold <= SB'(pslot(dP)); rkind <= R_NA; state <= S_RULE;       // read P
              end
            end else begin
              // binary ~ binary
              if (oob(dP)) begin
                tp = 1'b1; tpr = TR_OOB; tpp = dP;
              end else if (oob(dQ)) begin
                tp = 1'b1; tpr = TR_OOB; tpp = dQ;
              end else if (dlP && dlQ) begin
                nhold <= SB'(pslot(dP)); rkind <= R_BB; state <= S_RDQ;        // read P, then Q
              end else if (dlP || dlQ) begin
                nhold <= dlP ? SB'(pslot(dP)) : SB'(pslot(dQ)); rkind <= R_MIG; state <= S_RULE;
              end else begin
                if (can_send) begin snd = 1'b1; sf = {M_LINK, px(dP), py(dP), 64'd0, 64'd0, dQ, dP}; end
                else begin qp = 1'b1; qe = {K_LINK, dQ, dP}; end
              end
            end
          end
        end

        // ------------------------------------------------------------------ local var exchange (data from the var RAM)
        S_LVAR: if (vf_room != 0) begin
          logic [63:0] old;
          logic forged;
          logic [SB-1:0] sA;
          sA = SB'(pslot(A));
          forged = v_rd[67:64] != pown(A) && !MUT[16];
          old = v_rd[63:0];
          state <= S_IDLE;
          if (forged) begin tp = 1'b1; tpr = TR_FORGED; tpp = A; end
          if (forged && !MUT[20]) begin
            // dropped
          end else if (ptag(old) == T_NONE) begin
            v_we = 1'b1; v_wa = sA; v_wd = {v_rd[67:64], B};
          end else begin
            v_we = 1'b1; v_wa = sA; v_wd = {OWN_FREE, 64'd0};
            vf_push = 3'd1; vf_pd[0] = sA;
            ra <= old; rb <= B;            // continue linking old ~ B
            state <= MUT[11] ? S_IDLE : S_LINK;
          end
        end

        // ------------------------------------------------------------------ second node read
        S_RDQ: begin
          pdat <= n_rd[127:0];
          nhold <= SB'(pslot(rQ));
          if (nforged(nalloc[SB'(pslot(rP))], rP, n_rd)) begin tp = 1'b1; tpr = TR_FORGED; tpp = rP; state <= S_IDLE; end
          else state <= S_RULE;
        end

        // ------------------------------------------------------------------ apply a rule (node data from the node RAM)
        S_RULE: if (tq_room != 0 && nf_room >= 2 && 32'(nf_av) >= rneed_n && 32'(vf_av) >= rneed_v) begin
          logic [63:0] P, Q, a1, a2, b1, b2;
          logic [3:0] tP, tQ;
          logic [SB-1:0] sP, sQ;
          P = rP; Q = rQ;
          tP = ptag(P); tQ = ptag(Q);
          sP = SB'(pslot(P)); sQ = SB'(pslot(Q));
          state <= S_IDLE;
          if (rkind == R_NA) begin
            a1 = n_rd[63:0]; a2 = n_rd[127:64];
            if (nforged(nalloc[SB'(pslot(P))], P, n_rd)) begin
              tp = 1'b1; tpr = TR_FORGED; tpp = P;
            end else if (tP == T_SWI && tQ == T_NUM && pval(Q) != 0 && nf_tot == 0) begin
              qp = 1'b1; qe = {K_LINK, Q, P}; st_retry <= st_retry + 1;
            end else begin
              st_inter <= st_inter + 1;
              if (tQ == T_ERA || tQ == T_REF || tP == T_CON || tP == T_DUP) begin
                // erase / copy: both aux ports receive Q
                nf_push = 3'd1; nf_pd[0] = sP; nalloc[sP] <= 1'b0;
                pa[1] <= a2; pbv[1] <= (MUT[0] ? a1 : Q);
                ra <= a1; rb <= Q; pcnt <= 3'd1; state <= MUT[12] && tQ == T_ERA ? S_LINK : S_PUSH;
              end else if (tP == T_OPR) begin
                logic [3:0] op; logic s;
                op = P[47:44]; s = P[48];
                if (ptag(a1) == T_NUM) begin
                  logic [31:0] r;
                  r = s ? alu(op, pval(a1), pval(Q)) : alu(op, pval(Q), pval(a1));
                  if (MUT[8] && op == 4'd7) r = s ? alu(4'd9, pval(a1), pval(Q)) : alu(4'd9, pval(Q), pval(a1));
                  if (MUT[1]) r = alu(op, pval(a1), pval(Q));
                  nf_push = 3'd1; nf_pd[0] = sP; nalloc[sP] <= 1'b0;
                  ra <= a2; rb <= mkp(T_NUM, 16'd0, r); state <= S_LINK;
                end else begin
                  n_we = 1'b1; n_wa = sP; n_wd = {pown(P), a2, Q};       // reuse the slot for the flipped operator
                  ra <= a1; rb <= mkpo(T_OPR, {11'd0, MUT[2] ? s : ~s, op}, pown(P), here(sP)); state <= S_LINK;
                end
              end else begin  // SWI ~ NUM
                if (pval(Q) == 0) begin
                  n_we = 1'b1; n_wa = sP;
                  n_wd = {pown(P), MUT[9] ? {a2, ERA_P} : {ERA_P, a2}};    // (a2 *)
                  ra <= a1; rb <= mkpo(T_CON, 16'd0, pown(P), here(sP)); state <= S_LINK;
                end else begin
                  logic [SB-1:0] c2;
                  c2 = nf_top[0]; nf_pop = 3'd1;
                  n_we = 1'b1; n_wa = sP;
                  n_wd = {pown(P), a2, mkp(T_NUM, 16'd0, pval(Q) - (MUT[3] ? 32'd0 : 32'd1))};   // (#n-1 a2)
                  wq_a[0] <= c2; wq_d[0] <= {pown(P), mkpo(T_CON, 16'd0, pown(P), here(sP)), ERA_P}; wq_n <= 2'd1;  // (* c1)
                  nalloc[c2] <= 1'b1;
                  ra <= a1; rb <= mkpo(T_CON, 16'd0, pown(P), here(c2)); pcnt <= 3'd0; state <= S_PUSH;
                end
              end
            end
          end else if (rkind == R_BB) begin
            logic anni;
            a1 = pdat[63:0]; a2 = pdat[127:64];
            b1 = n_rd[63:0]; b2 = n_rd[127:64];
            anni = (tP == tQ) && (plab(P) == plab(Q)) && (tP == T_CON || tP == T_DUP);
            if (MUT[4]) anni = (tP == tQ) && (tP == T_CON || tP == T_DUP);
            if (nforged(nalloc[SB'(pslot(Q))], Q, n_rd)) begin
              tp = 1'b1; tpr = TR_FORGED; tpp = Q;
            end else if (!anni && (nf_tot < 2 || vf_tot < 4)) begin
              qp = 1'b1; qe = {K_LINK, Q, P}; st_retry <= st_retry + 1;
            end else if (anni) begin
              st_inter <= st_inter + 1;
              nf_push = 3'd2; nf_pd[0] = sP; nf_pd[1] = sQ; nalloc[sP] <= 1'b0; nalloc[sQ] <= 1'b0;
              pa[1] <= a2; pbv[1] <= b2;
              ra <= a1; rb <= (MUT[5] ? b2 : b1); pcnt <= 3'd1; state <= S_PUSH;
            end else begin
              logic [SB-1:0] n1, n3, v0, v1, v2, v3;
              logic [63:0] x11, x12, x21, x22;
              logic [3:0] o;
              st_inter <= st_inter + 1;
              o = pown(P);
              n1 = nf_top[0]; n3 = nf_top[1]; nf_pop = 3'd2;
              v0 = vf_top[0]; v1 = vf_top[1]; v2 = vf_top[2]; v3 = vf_top[3]; vf_pop = 3'd4;
              x11 = mkpo(T_VAR, 16'd0, o, here(v0)); x12 = mkpo(T_VAR, 16'd0, o, here(v1));
              x21 = mkpo(T_VAR, 16'd0, o, here(v2)); x22 = mkpo(T_VAR, 16'd0, o, here(MUT[14] ? v2 : v3));
              n_we = 1'b1; n_wa = sP; n_wd = {o, x12, x11};                       // copy 1 of Q's kind
              wq_a[0] <= n1; wq_d[0] <= {o, x22, x21};                             // copy 2 of Q's kind
              wq_a[1] <= sQ; wq_d[1] <= {o, x21, x11};                             // copy 1 of P's kind
              wq_a[2] <= n3; wq_d[2] <= {o, MUT[6] ? {x12, x22} : {x22, x12}};     // copy 2 of P's kind
              wq_n <= 2'd3;
              v_we = 1'b1; v_wa = v0; v_wd = {o, 64'd0};                           // owner tags of the fresh vars
              vq_a[0] <= v1; vq_a[1] <= v2; vq_a[2] <= v3; vq_n <= 2'd3; vq_o <= o;
              nalloc[n1] <= 1'b1; nalloc[n3] <= 1'b1;
              pa[1] <= a2; pbv[1] <= withpay(Q, here(n1));
              pa[2] <= b1; pbv[2] <= withpay(P, here(sQ));
              pa[3] <= b2; pbv[3] <= withpay(P, here(n3));
              ra <= a1; rb <= withpay(Q, here(sP)); pcnt <= 3'd3; state <= S_PUSH;
            end
          end else begin
            // R_MIG: one side local -> migrate the local node to the partner's cell (MSG NODE)
            logic [63:0] L, R;
            logic lP;
            lP = local_p(P) && !oob(P);
            L = lP ? P : Q; R = lP ? Q : P;
            if (nforged(nalloc[SB'(pslot(L))], L, n_rd)) begin
              tp = 1'b1; tpr = TR_FORGED; tpp = L;
            end else if (can_send) begin
              snd = 1'b1; sf = {M_NODE, px(R), py(R), R, n_rd[127:64], n_rd[63:0], L};
              nf_push = 3'd1; nf_pd[0] = SB'(pslot(L)); nalloc[SB'(pslot(L))] <= 1'b0;
            end else begin qp = 1'b1; qe = {K_LINK, Q, P}; st_retry <= st_retry + 1; end
          end
        end

        // ------------------------------------------------------------------ push extra links and drain queued writes, then continue with (ra, rb)
        S_PUSH: if (tq_room != 0) begin
          if (pcnt != 0) begin qp = 1'b1; qe = {K_LINK, pbv[pcnt[1:0]], pa[pcnt[1:0]]}; pcnt <= pcnt - 1; end
          if (wq_n != 0) begin
            n_we = 1'b1; n_wa = wq_a[wq_n - 1]; n_wd = wq_d[wq_n - 1]; wq_n <= wq_n - 1;
          end
          if (vq_n != 0) begin
            v_we = 1'b1; v_wa = vq_a[vq_n - 1]; v_wd = {vq_o, 64'd0}; vq_n <= vq_n - 1;
          end
          if (pcnt <= 1 && wq_n <= 1 && vq_n <= 1) state <= S_LINK;
        end

        // ------------------------------------------------------------------ choose where a REF expands
        S_SPAWN: begin
          // give the expansion to a hungry neighbour if there is one, otherwise expand here
          hrot <= hrot + 2'd1;
          if (!hv_found || !can_send || MUT[7]) begin
            ex_x <= sp_x; state <= S_EX0;
          end else begin
            snd = 1'b1; sf = {M_SPAWN, dir_x(hv_dir), dir_y(hv_dir), 64'd0, 64'd0, sp_x, mkpo(T_REF, sp_ref, sp_own, 32'd0)};
            state <= S_IDLE;
          end
        end

        // ------------------------------------------------------------------ EXPAND: directory read, header read
        S_EX0: state <= S_EX1;                 // dir read issued (d_ra = sp_ref)
        S_EX1: state <= S_EX2;                 // header read issued (r_ra = dir)
        S_EX2: if (tq_room != 0) begin
          logic [7:0] nn, nv, nr;
          nn = r_rd[71:64]; nv = r_rd[79:72]; nr = r_rd[87:80];
          if ((SB+2)'(nn) <= nf_tot && (SB+2)'(nv) <= vf_tot && (32'(tq_tot) + 32'(nr) + 1) < QDEPTH) begin
            ex_base <= d_rd + 1; ex_nn <= nn; ex_nv <= nv; ex_nr <= nr; ex_root <= r_rd[63:0];
            ex_own <= sp_own; ex_i <= 8'd0;
            state <= S_EXA;
          end else if (NT > 1) begin
            // not enough room here: forward the SPAWN to a neighbour
            logic [2:0] t;
            t = (rr == 3'd0) ? 3'd1 : rr;
            rr <= (t == 3'(NT - 1)) ? 3'd0 : t + 1;
            st_retry <= st_retry + 1;
            if (can_send) begin snd = 1'b1; sf = {M_SPAWN, tx[t], ty[t], 64'd0, 64'd0, ex_x, mkpo(T_REF, sp_ref, sp_own, 32'd0)}; end
            else begin qp = 1'b1; qe = {K_SPAWN, ex_x, mkpo(T_REF, sp_ref, sp_own, 32'd0)}; end
            state <= S_IDLE;
          end else begin
            err <= 4'd2; state <= S_HALT;    // out of memory on a 1x1 fabric
          end
        end

        // pass 1: allocate one node slot and one var slot per cycle into the maps; tag the vars
        S_EXA: begin
          logic needn, needv;
          needn = ex_i < ex_nn; needv = ex_i < ex_nv;
          if ((!needn || nf_av != 0) && (!needv || vf_av != 0)) begin
            if (needn) begin nmap[XB'(ex_i)] <= nf_top[0]; nf_pop = 3'd1; end
            if (needv) begin
              vmap[XB'(ex_i)] <= vf_top[0]; vf_pop = 3'd1;
              v_we = 1'b1; v_wa = vf_top[0]; v_wd = {MUT[19] ? 4'd0 : ex_own, 64'd0};
            end
            ex_i <= ex_i + 1;
            if (ex_i + 1 >= ex_nn && ex_i + 1 >= ex_nv) begin
              ex_i <= 8'd0;
              state <= (ex_nn != 0) ? S_EXN : S_EXR;   // r_ra = ex_base: template node 0 is being read
            end
          end
        end

        // pass 2: one template node per cycle (ROM read pipelined one ahead)
        S_EXN: begin
          logic [SB-1:0] s;
          s = nmap[XB'(ex_i)];
          n_we = 1'b1; n_wa = s; n_wd = {MUT[19] ? 4'd0 : ex_own, `TR(r_rd[127:64]), `TR(r_rd[63:0])};
          nalloc[s] <= 1'b1;
          ex_i <= ex_i + 1;
          if (ex_i == ex_nn - 1) begin ex_i <= 8'd0; state <= S_EXR; end
        end

        S_EXR: if (tq_room != 0) begin
          if (ex_i < ex_nr) begin
            qp = 1'b1; qe = {K_LINK, `TR(r_rd[127:64]), `TR(r_rd[63:0])};
            ex_i <= ex_i + 1;
          end else begin
            ra <= `TR(ex_root); rb <= ex_x; state <= S_LINK;
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
      tq_push = 3'd0; tq_pd[0] = qe;
      if (qp) begin
        if (tq_tot >= (QB+2)'(QDEPTH)) begin err <= 4'd1; state <= S_HALT; end
        else begin
          tq_push = 3'd1;
          if (32'(tq_tot) + 1 > st_maxq) st_maxq <= 32'(tq_tot) + 1;
        end
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

      // ---- memory ports: one write and one registered read per array ----
      if (n_we) node_mem[n_wa] <= n_wd;
      if (v_we) var_mem[v_wa] <= v_wd;

      // ---- stack caches: pops, pushes, refill arrival, spill / refill (one SRAM access each per cycle) ----
      `CSTACK(nc, ncnt, nsp, npend, nstk, nstk_rd, NK, 5, 4, nf_pop, nf_push, nf_pd, 2, SLOTS, SB, SB, nc_n)
      `CSTACK(vc, vcnt, vsp, vpend, vstk, vstk_rd, VK, 6, 5, vf_pop, vf_push, vf_pd, 1, SLOTS, SB, SB, vc_n)
      `CSTACK(qc, qcnt, qsp, qpend, tqm, tqm_rd, QK, 3, 2, tq_pop, tq_push, tq_pd, 1, QDEPTH, 130, QB, qc_n)
    end
    n_rd <= node_mem[n_ra];
    v_rd <= var_mem[v_ra];
    if (cfg_we && !cfg_dir) rom[RB'(cfg_a)] <= cfg_d;
    if (cfg_we && cfg_dir) dirm[DB'(cfg_a)] <= cfg_d[15:0];
    r_rd <= rom[r_ra];
    d_rd <= dirm[d_ra];
  end


`ifndef SYNTHESIS
  // ---------------- debug trace (+trace) ----------------
  bit trace_on;
  initial trace_on = $test$plusargs("trace");
  always @(posedge clk) if (trace_on && !rst && state != S_INIT)
    $display("c%0d,%0d st=%0d ra=%h rb=%h q=%0d/%0d/%0d top=%h rd=%h m1=%h nf=%0d vf=%0d inter=%0d", X, Y, state, ra, rb, qcnt, qsp, qpend, tq_top, tqm_rd, tqm[1], nf_tot, vf_tot, st_inter);
  // ---------------- dump (testbench) ----------------
  always @(posedge clk) begin
    if (dump) begin
      int fd;
      for (int i = 0; i < SLOTS; i++) na_out[i] = nalloc[i];
      $writememh($sformatf("%s/out_nalloc_%0d_%0d.hex", outdir, X, Y), na_out);
      $writememh($sformatf("%s/out_node_%0d_%0d.hex", outdir, X, Y), node_mem);
      $writememh($sformatf("%s/out_var_%0d_%0d.hex", outdir, X, Y), var_mem);
      fd = $fopen($sformatf("%s/out_stats_%0d_%0d.txt", outdir, X, Y), "w");
      $fwrite(fd, "cycles %0d\ninteractions %0d\nbusy %0d\ntasks %0d\nlinks %0d\nretry %0d\nmsg_link %0d\nmsg_node %0d\nmsg_spawn %0d\nmaxq %0d\nfree_nodes %0d\nfree_vars %0d\nerr %0d\npeak_nodes %0d\npeak_vars %0d\ntraps %0d\ntrap_reason %0d\ntrap_owner %0d\ntrap_addr %0d\ntrap_mask %0d\n",
              cyc, st_inter, st_busy, st_tasks, st_links, st_retry, st_msg0, st_msg1, st_msg2, st_maxq, nf_tot, vf_tot, err, SLOTS - st_minfn, SLOTS - st_minfv, st_traps, tr_reason, tr_owner, tr_addr, tr_mask);
      $fclose(fd);
    end
  end
`endif
endmodule
