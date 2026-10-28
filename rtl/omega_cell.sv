// TACHYON-Omega active memory cell (v3: SRAM-style storage, one link step per cycle).
//
// Storage is written so that synthesis infers 1R1W synchronous SRAM macros (one write statement and
// one registered read per array):
//   node RAM  SLOTS x 132 b  {owner[3:0], aux2, aux1}   2R1W (two read ports: both nodes of a redex)
//   var RAM   SLOTS x 68 b   {owner[3:0], substitution}
//   free node / free var stacks and the task stack: a K-entry register top cache over a 1R1W SRAM
//   (CSTACK macro); definition node ROM, redex ROM and directory: synchronous 1R ROMs (with a loader
//   write port).  Every read address is computed one cycle ahead from the engine's NEXT state
//   (look-ahead), so a link step finds its var / node data already read: one link step per cycle.
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
  parameter int RDXSZ = 2048,               // redex template ROM entries
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
  output logic        roomy,               // to neighbours: free node and var slots above the watermark
  input  logic [3:0]  nbr_roomy,           // from neighbours N, E, S, W
  output logic        ready,               // initialisation finished
  output logic [3:0]  err,
  input  logic        dump,
  // cluster definition ROM (omega_rom, shared by the cells of a cluster; SPEC 5.6): request / grant,
  // data one cycle after the grant
  output logic        rom_req,
  output logic [15:0] rom_an, rom_ar,
  input  logic        rom_gnt,
  input  logic [511:0] rom_dn, rom_dr,     // one ROM word = four template entries
  // loader port for the per-cell directory (simulation preloads it with $readmemh)
  input  logic        cfg_we,
  input  logic [1:0]  cfg_sel,             // 2 = directory
  input  logic [15:0] cfg_a,
  input  logic [127:0] cfg_d,
  output logic [31:0] st_inter
);
  `include "omega_funcs.svh"
  localparam int SB = $clog2(SLOTS);
  localparam int QB = $clog2(QDEPTH);
  localparam int OB = $clog2(DEPTH);
  localparam int RB = $clog2(ROMSZ);
  localparam int RRB = $clog2(RDXSZ);
  localparam int DB = $clog2(DIRSZ);
  localparam int XB = $clog2(XMAP);
  localparam logic [63:0] ERA_P = 64'h3000_0000_0000_0000;

  typedef enum logic [2:0] {S_INIT, S_IDLE, S_LINK, S_WQ, S_EXA, S_EXN, S_HALT} st_t;
  st_t state;

  // Memories: every array below has exactly one write statement and one registered read (end of the
  // sequential block), so synthesis infers 1R1W synchronous SRAMs (ROM/dir: 1R).
  logic [131:0] node_mem [SLOTS];       // {owner, aux2, aux1}
  logic [67:0]  var_mem  [SLOTS];       // {owner, substitution}
  logic [127:0] dirm [DIRSZ];           // {root[63:0], 8'0, nr, nv, nn, rbase[15:0], nbase[15:0]}
  logic [SB-1:0] nstk [SLOTS];          // free node stack (SRAM part)
  logic [SB-1:0] vstk [SLOTS];          // free var stack (SRAM part)
  logic [129:0] tqm  [QDEPTH];          // task stack (SRAM part) {kind, b, a}
  // synchronous read data
  logic [131:0] n_rd, n_rd2;  logic [67:0] v_rd, v_rd2;  logic [127:0] rn0, rr0, rn1, rr1, d_rd;
  logic rom_v;                          // rom_dn / rom_dr carry the template word requested last cycle (rvp)
  logic [511:0] bufn, bufr;             // last template word received (node / redex)
  logic [6:0]   bufp, rvp;              // word index within the definition: buffered / arriving
  logic         bufok;
  logic [SB-1:0] nstk_rd, vstk_rd;  logic [129:0] tqm_rd;
  // stack top caches (registers): c[0] bottom .. c[cnt-1] top; sp = entries in the SRAM part
  localparam int NK = 14, VK = 14, QK = 8;    // (4-bit cache counters: K + pushes <= 15)
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
    $readmemh($sformatf("%s/dir.hex", imgdir), dirm);
  end
`else
  initial qinit[0] = '0;
`endif

  logic [7:0][SB-1:0] nf_top;
  logic [7:0][SB-1:0] vf_top;
  logic [129:0]   tq_top;
  logic [3:0]     nf_av, nf_room, vf_av, vf_room, tq_av, tq_room;
  logic [SB+1:0]  nf_tot, vf_tot;
  logic [QB+1:0]  tq_tot;
  always_comb begin
    for (int i = 0; i < 8; i++) nf_top[i] = (32'(ncnt) > i) ? nc[32'(ncnt) - 1 - i] : '0;
    for (int i = 0; i < 8; i++) vf_top[i] = (32'(vcnt) > i) ? vc[32'(vcnt) - 1 - i] : '0;
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
  // memory-pressure target: first roomy existing neighbour in rotating order (SPEC 9)
  logic       rv_found;
  logic [1:0] rv_dir;
  logic [1:0] mrot;
  always_comb begin
    rv_found = 1'b0; rv_dir = 2'd0;
    for (int k = 0; k < 4; k++) begin
      logic [1:0] d;
      d = 2'(mrot + 2'(k));
      if (!rv_found && EXISTS[d] && nbr_roomy[d] && !MUT[27]) begin rv_found = 1'b1; rv_dir = d; end
    end
  end
  function automatic logic [3:0] dir_x(input logic [1:0] d);
    dir_x = (d == 2'd1) ? 4'(X + 1) : (d == 2'd3) ? 4'(X - 1) : 4'(X);
  endfunction
  function automatic logic [3:0] dir_y(input logic [1:0] d);
    dir_y = (d == 2'd0) ? 4'(Y - 1) : (d == 2'd2) ? 4'(Y + 1) : 4'(Y);
  endfunction

  // ---------------- var-hop unit (VHU, step 9): a second engine for substitution chains ----------------
  // The main engine hands a link whose A side is a local var (and that needs no check it cannot do)
  // to the VHU instead of following the chain itself, and picks its next task in the same cycle.
  // The VHU does one var exchange per cycle on its own var RAM read port (read ahead like the main
  // engine's) and var write port 2: an empty var takes B and the VHU is free again; a substituted var
  // is freed and the chain continues while the next link again has a local var on one side; any
  // other link (a redex, a remote var, a check that fails) is handed back through `vh_o*` and taken
  // by the main engine as its next task, before the task stack.  The VHU yields write port 2 to the
  // main engine and stalls when the main engine's current link names the same var slot, so every var
  // exchange stays atomic (single owner, one exchange at a time).
  logic        vh_v;                    // VHU holds a link (busy)
  logic [63:0] vh_a, vh_b;              // its link: vh_a = local var
  logic        vh_ov;                   // hand-back: link for the main engine
  logic [63:0] vh_oa, vh_ob;
  logic [31:0] st_vhu;

  // ---------------- engine registers ----------------
  logic [63:0] ra, rb;                  // current link (its RAM data was read one cycle ahead)
  logic        rsp, rsx, rfw;            // rfw: PULL second half (send LINK to the partner's cell)
  logic        ej_taken;                // the eject head was consumed last cycle: pop it now (registered pop)                // (ra = REF, rb = partner) is a spawn request: rsp = retry task
                                        // (already counted), rsx = SPAWN message (expand here or forward)
  logic [2:0][SB-1:0] wq_a;             // queued node writes (commutation / SWI), drained in S_WQ
  logic [2:0][131:0]  wq_d;
  logic [1:0]    wq_n;
  logic [2:0][SB-1:0] vq_a;             // queued var owner-tag writes (commutation)
  logic [1:0]    vq_n;
  logic [3:0]    vq_o;
  logic [3:0]  ex_own;
  logic [31:0] st_traps, tr_addr;
  logic [1:0]  tr_reason;
  logic [3:0]  tr_owner;
  logic [47:0] tr_mask;                 // (reason, owner) pairs seen: bit (reason-1)*16 + owner
  logic [2:0]  rr;
  logic [15:0] ex_nbase, ex_rbase, ex_ref;
  logic [7:0]  ex_nn, ex_nv, ex_nr, ex_i, ex_in, ex_iv;
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
  // order a link: A = var side if any; P / Q = the pair ordered by (tag, label), bigger first
  function automatic logic [63:0] ordA(input logic [63:0] x, input logic [63:0] y);
    ordA = (!is_var(x) && is_var(y)) ? y : x;
  endfunction
  function automatic logic [63:0] ordB(input logic [63:0] x, input logic [63:0] y);
    ordB = (!is_var(x) && is_var(y)) ? x : y;
  endfunction
  function automatic logic qfirst(input logic [63:0] a, input logic [63:0] b);   // b is P
    qfirst = ptag(a) < ptag(b) || (ptag(a) == ptag(b) && plab(a) < plab(b));
  endfunction

  // ---------------- link decode (combinational, from ra/rb) ----------------
  logic [63:0] A, B, dP, dQ;
  logic        dvar, dlP, dlQ;
  always_comb begin
    A = ordA(ra, rb); B = ordB(ra, rb);
    dvar = is_var(A);
    if (qfirst(A, B)) begin dP = B; dQ = A; end else begin dP = A; dQ = B; end
    dlP = is_node(dP) && !oob(dP) && local_p(dP);
    dlQ = is_node(dQ) && !oob(dQ) && local_p(dQ);
  end

  // ---------------- source selection inputs ----------------
  logic can_send, q_ok, stall_now, rnd_msg;
  assign ej_pop = ej_taken;
  always_comb begin
    can_send  = ob_cnt < (OB+1)'(DEPTH);
    q_ok      = tq_av != 0;
    stall_now = (stall != 0) && (erng[7:0] < stall);
    rnd_msg   = erng[15:8] < pmsg;
    idle      = (state == S_IDLE) && (tq_tot == 0) && !ej_v && (ob_cnt == 0) && (!rbusy || MUT[15]) && !vh_v;
    ready     = state != S_INIT;
    hungry    = (state == S_IDLE) && (tq_tot == 0) && !ej_v && (roomy || MUT[28]) && !vh_v;
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

  // ---------------- EXPAND datapath + cluster ROM request (combinational from registers only) ----
  // v4 EXPAND writes TWO template entries per cycle: node i and i+1 (node RAM write ports 1 and 2),
  // var tags i and i+1 (var RAM write ports 1 and 2), redexes i and i+1 (two task pushes).  Slot
  // allocation maps up to 8 node + 8 var slots per cycle from the free-stack caches (first batch in
  // the rule cycle; the rest in S_EXN cycles that write nothing yet, since a template port may name
  // any node / var of the definition); then entries are written once their template word is here.
  // The templates are stored as words of FOUR entries (the loader aligns every definition to a
  // multiple of four), so one grant of the cluster ROM feeds two EXPAND cycles.  The cell keeps the
  // last word it received (bufn/bufr) and uses an arriving word directly (bypass).  The request for
  // the word the NEXT cycle needs is made from the current registered state: in S_EXN the first word
  // of entries {i', i'+1} (i' = ex_i after this cycle) that is neither buffered nor arriving; in S_LINK
  // word 0 of the definition whose directory word was read ahead, when the link may start an expansion
  // here (dQ is a REF not handed to a hungry neighbour).  A missed grant just holds S_EXN.
  logic [7:0] ex_lrom, ex_lst;          // entries read from the ROM: max(nn, nr); entries in all: max(nn, nv, nr)
  logic       ex_e0, ex_e1;             // entry ex_i / ex_i + 1 is written this cycle
  logic [7:0] ex_adv;
  logic [6:0] rom_q;                    // word requested this cycle
  function automatic logic [127:0] wsel(input logic [511:0] w, input logic [1:0] k);
    wsel = (k == 2'd0) ? w[127:0] : (k == 2'd1) ? w[255:128] : (k == 2'd2) ? w[383:256] : w[511:384];
  endfunction
  always_comb begin
    logic [7:0] j0, j1, ni, ni1;
    logic a0, a1, h0, h1, ok0, ok1, nbok, c1, c2;
    logic [6:0] q0, q1, nbp;
    logic [511:0] w0n, w0r, w1n, w1r;
    logic [15:0] nb, rb2;
    logic [1:0] k0, k1;
    ex_lrom = (ex_nn > ex_nr) ? ex_nn : ex_nr;
    ex_lst = (ex_lrom > ex_nv) ? ex_lrom : ex_nv;
    j0 = ex_i; j1 = ex_i + 8'd1;
    q0 = j0[7:2]; q1 = j1[7:2];
    a0 = rom_v && rvp == q0; h0 = a0 || (bufok && bufp == q0);
    a1 = rom_v && rvp == q1; h1 = a1 || (bufok && bufp == q1);
    w0n = a0 ? rom_dn : bufn; w0r = a0 ? rom_dr : bufr;
    w1n = a1 ? rom_dn : bufn; w1r = a1 ? rom_dr : bufr;
    k0 = j0[1:0] ^ {1'b0, MUT[26]}; k1 = j1[1:0] ^ {1'b0, MUT[26]};
    rn0 = wsel(w0n, k0); rr0 = wsel(w0r, k0); rn1 = wsel(w1n, k1); rr1 = wsel(w1r, k1);
    // every slot of the definition must be mapped first: template ports reference any node / var
    ok0 = j0 < ex_lst && ex_in >= ex_nn && ex_iv >= ex_nv && (j0 >= ex_lrom || h0 || MUT[30]) && tq_room != 0;
    ok1 = ok0 && j1 < ex_lst && (j1 >= ex_lrom || h1 || MUT[30]) && tq_room >= 4'd2;
    ex_e0 = state == S_EXN && ok0;
    ex_e1 = state == S_EXN && ok1;
    ex_adv = (MUT[34] && ex_e0) ? 8'd2 : 8'(ex_e0) + 8'(ex_e1);
    nbp = rom_v ? rvp : bufp; nbok = rom_v || bufok;    // buffer contents next cycle
    ni = ex_i + ex_adv; ni1 = ni + 8'd1;
    c1 = ni < ex_lrom && !(nbok && nbp == ni[7:2]);
    c2 = ni1 < ex_lrom && !(nbok && nbp == ni1[7:2]);
    rom_req = 1'b0; rom_q = '0; nb = ex_nbase; rb2 = ex_rbase;
    if (state == S_EXN) begin
      rom_req = c1 || c2;
      rom_q = c1 ? ni[7:2] : ni1[7:2];
    end else if (state == S_LINK && ptag(dQ) == T_REF && (rsp || rsx || !(hv_found && can_send && !MUT[7]))) begin
      rom_req = 1'b1; nb = d_rd[15:0]; rb2 = d_rd[31:16];       // (the buffer is cleared when the expansion starts)
    end
    rom_an = (nb >> 2) + 16'(rom_q); rom_ar = (rb2 >> 2) + 16'(rom_q);
  end

  // Per-cycle temporaries of the sequential block (blocking-assigned first thing every cycle, so
  // synthesis keeps them combinational; declared here because Yosys mishandles packed-array locals).
  logic snd; flit_t sf;
  logic [1:0] pn; logic [2:0][129:0] pq;          // task pushes this cycle (up to 3)
  logic tp; logic [1:0] tpr; logic [63:0] tpp;
  logic fin;                                      // the current step is done: pick new work this cycle
  st_t  nst;
  logic [63:0] nra, nrb; logic nrsp, nrsx, nrfw;
  logic [3:0] nf_pop, vf_pop;
  logic [2:0] nf_push, vf_push, tq_pop, tq_push;
  logic [1:0][SB-1:0] nf_pd; logic [1:0][SB-1:0] vf_pd;
  logic hand; logic [63:0] nvh_a, nvh_b; logic nvh_v, vh_go; logic [SB-1:0] la_v2;
  logic [2:0][129:0] tq_pd;
  logic n_we, v_we; logic [SB-1:0] n_wa, v_wa; logic [131:0] n_wd; logic [67:0] v_wd;
  logic n_we2, v_we2; logic [SB-1:0] n_wa2, v_wa2; logic [131:0] n_wd2; logic [67:0] v_wd2;   // second write ports
  logic [NK-1:0][SB-1:0] nc_n; logic [VK-1:0][SB-1:0] vc_n; logic [QK-1:0][129:0] qc_n;
  logic [4:0] cs_m, cs_after; logic cs_spill, cs_fill;
  logic [SB-1:0] la_v, la_n1, la_n2; logic [DB-1:0] la_d;
  logic [63:0] la_A, la_B, la_P, la_Q;
  logic alloc, al_start; logic [7:0] al_nn, al_nv, al_in, al_iv;
  logic [3:0] al_kn, al_kv;
  logic sp_go; logic [63:0] sp_ref_p, sp_x_p; logic sp_local_only;

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
      vh_v <= 1'b0; vh_ov <= 1'b0; st_vhu <= '0;
      wq_n <= '0; vq_n <= '0; bufok <= 1'b0; rom_v <= 1'b0; rsp <= 1'b0; rsx <= 1'b0; rfw <= 1'b0; ej_taken <= 1'b0;
      roomy <= 1'b0; mrot <= 2'(X + Y + 1);
      ncnt <= '0; nsp <= '0; npend <= 1'b0;
      vcnt <= '0; vsp <= '0; vpend <= 1'b0;
      qcnt <= '0; qsp <= (QB+1)'(qinit[0]); qpend <= 1'b0;
    end else begin
      snd = 1'b0; sf = '0; pn = '0; pq = '0;
      tp = 1'b0; tpr = '0; tpp = '0;
      fin = 1'b0; nst = state; nra = ra; nrb = rb; nrsp = rsp; nrsx = rsx; nrfw = rfw;
      nf_pop = '0; nf_push = '0; nf_pd = '0;
      vf_pop = '0; vf_push = '0; vf_pd = '0;
      tq_pop = '0;
      n_we = 1'b0; n_wa = '0; n_wd = '0;
      v_we = 1'b0; v_wa = '0; v_wd = '0;
      n_we2 = 1'b0; n_wa2 = '0; n_wd2 = '0;
      v_we2 = 1'b0; v_wa2 = '0; v_wd2 = '0;
      alloc = 1'b0; al_start = 1'b0;
      hand = 1'b0; nvh_a = vh_a; nvh_b = vh_b; nvh_v = vh_v; vh_go = 1'b0; al_nn = '0; al_nv = '0; al_in = '0; al_iv = '0; al_kn = '0; al_kv = '0;
      sp_go = 1'b0; sp_ref_p = '0; sp_x_p = '0; sp_local_only = 1'b0;
      erng <= xorshift(erng);
      ej_taken <= 1'b0;
      if (rom_v) begin bufn <= rom_dn; bufr <= rom_dr; bufp <= rvp; bufok <= 1'b1; end
      if (state != S_INIT && nf_tot < st_minfn) st_minfn <= nf_tot;
      if (state != S_INIT && vf_tot < st_minfv) st_minfv <= vf_tot;
      if (state != S_INIT) cyc <= cyc + 1;
      // roomy with hysteresis: set above SLOTS/4 free node and var slots, cleared below SLOTS/8
      if (state != S_INIT) begin
        if (nf_tot >= (SB+2)'(SLOTS / 4) && vf_tot >= (SB+2)'(SLOTS / 4)) roomy <= 1'b1;
        else if (nf_tot < (SB+2)'(SLOTS / 8) || vf_tot < (SB+2)'(SLOTS / 8)) roomy <= 1'b0;
      end
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
            if (init_i == 1) fin = 1'b1;
          end
        end

        S_IDLE: fin = 1'b1;

        // ------------------------------------------------------------------ one link step (data read ahead)
        S_LINK: if (tq_room >= 4'd3 && nf_room >= 4'd2 && vf_room != 0) begin
          logic rmt;
          logic [3:0] tP, tQ;
          rmt = dvar ? leaves(A) : ((is_node(A) && leaves(A)) || (is_node(B) && leaves(B)));
          tP = ptag(dP); tQ = ptag(dQ);
          nrsp = 1'b0; nrsx = 1'b0; nrfw = 1'b0;
          if (xown(A, B) && !(fi[0] && rmt && !rsx)) begin
            tp = 1'b1; tpr = TR_CROSS; tpp = lowown(A, B); fin = 1'b1;
          end else if (rfw) begin
            // PULL, second half: ask the partner's cell for its node (its NODE rule migrates it here)
            if (oob(ra)) begin tp = 1'b1; tpr = TR_OOB; tpp = ra; end
            else if (can_send) begin snd = 1'b1; sf = {M_LINK, px(ra), py(ra), 64'd0, 64'd0, rb, ra}; end
            else begin pn = 2'd1; pq[0] = {K_FWD, rb, ra}; st_retry <= st_retry + 1; end
            fin = 1'b1;
          end else if (rsp || rsx) begin
            sp_go = 1'b1; sp_ref_p = dQ; sp_x_p = dP; sp_local_only = rsx;
          end else if (dvar) begin
            st_links <= st_links + 1;
            if (oob(A)) begin
              tp = 1'b1; tpr = TR_OOB; tpp = A; fin = 1'b1;
            end else if (local_p(A)) begin
              logic [63:0] old;
              logic forged;
              forged = v_rd[67:64] != pown(A) && !MUT[16];
              old = v_rd[63:0];
              if (forged) begin tp = 1'b1; tpr = TR_FORGED; tpp = A; end
              if (forged && !MUT[20]) begin
                fin = 1'b1;                    // dropped
              end else if (ptag(old) == T_NONE) begin
                v_we = 1'b1; v_wa = SB'(pslot(A)); v_wd = {v_rd[67:64], B};
                fin = 1'b1;
              end else begin
                v_we = 1'b1; v_wa = SB'(pslot(A)); v_wd = {OWN_FREE, 64'd0};
                vf_push = 3'd1; vf_pd[0] = SB'(pslot(A));
                nra = old; nrb = B;            // continue linking old ~ B (next cycle)
                if (MUT[11]) fin = 1'b1;
              end
            end else begin
              if (can_send) begin snd = 1'b1; sf = {M_LINK, px(A), py(A), 64'd0, 64'd0, B, A}; end
              else begin pn = 2'd1; pq[0] = {K_LINK, B, A}; end
              fin = 1'b1;
            end
          end else if (tP <= T_NUM) begin
            // nullary ~ nullary
            st_inter <= st_inter + 1;
            if (tQ == T_REF && tP != T_ERA) begin sp_go = 1'b1; sp_ref_p = dQ; sp_x_p = dP; end
            else fin = 1'b1;
          end else if (tQ <= T_NUM) begin
            // binary node P ~ nullary Q (node P read ahead on port 1)
            logic [63:0] a1, a2;
            a1 = n_rd[63:0]; a2 = n_rd[127:64];
            if (tQ == T_REF && (tP != T_DUP || MUT[13])) begin
              st_inter <= st_inter + 1;
              sp_go = 1'b1; sp_ref_p = dQ; sp_x_p = dP;
            end else if (oob(dP)) begin
              tp = 1'b1; tpr = TR_OOB; tpp = dP; fin = 1'b1;
            end else if (!local_p(dP)) begin
              if (can_send) begin snd = 1'b1; sf = {M_LINK, px(dP), py(dP), 64'd0, 64'd0, dQ, dP}; end
              else begin pn = 2'd1; pq[0] = {K_LINK, dQ, dP}; end
              fin = 1'b1;
            end else if (nforged(nalloc[SB'(pslot(dP))], dP, n_rd)) begin
              tp = 1'b1; tpr = TR_FORGED; tpp = dP; fin = 1'b1;
            end else if (tP == T_SWI && tQ == T_NUM && pval(dQ) != 0 && nf_tot == 0) begin
              if (rv_found && can_send) begin
                // no free slot: move the SWI node to a roomy neighbour (it applies the rule there)
                snd = 1'b1; sf = {M_NODE, dir_x(rv_dir), dir_y(rv_dir), dQ, a2, a1, dP};
                nf_push = 3'd1; nf_pd[0] = SB'(pslot(dP)); nalloc[SB'(pslot(dP))] <= 1'b0; mrot <= mrot + 2'd1;
              end else begin pn = 2'd1; pq[0] = {K_LINK, dQ, dP}; st_retry <= st_retry + 1; end
              fin = 1'b1;
            end else if (tP == T_SWI && tQ == T_NUM && pval(dQ) != 0 && nf_av == 0) begin
              // wait for the free-node cache to refill (hold: same link, same read-ahead)
            end else begin
              logic [SB-1:0] sP;
              sP = SB'(pslot(dP));
              st_inter <= st_inter + 1;
              if (tQ == T_ERA || tQ == T_REF || tP == T_CON || tP == T_DUP) begin
                // erase / copy: both aux ports receive Q
                nf_push = 3'd1; nf_pd[0] = sP; nalloc[sP] <= 1'b0;
                if (MUT[12] && tQ == T_ERA) pn = 2'd0;
                else begin pn = 2'd1; pq[0] = {K_LINK, (MUT[0] ? a1 : dQ), a2}; end
                nra = a1; nrb = dQ;
              end else if (tP == T_OPR) begin
                logic [3:0] op; logic s;
                op = dP[47:44]; s = dP[48];
                if (ptag(a1) == T_NUM) begin
                  logic [31:0] r;
                  r = s ? alu(op, pval(a1), pval(dQ)) : alu(op, pval(dQ), pval(a1));
                  if (MUT[8] && op == 4'd7) r = s ? alu(4'd9, pval(a1), pval(dQ)) : alu(4'd9, pval(dQ), pval(a1));
                  if (MUT[1]) r = alu(op, pval(a1), pval(dQ));
                  nf_push = 3'd1; nf_pd[0] = sP; nalloc[sP] <= 1'b0;
                  nra = a2; nrb = mkp(T_NUM, 16'd0, r);
                end else begin
                  n_we = 1'b1; n_wa = sP; n_wd = {pown(dP), a2, dQ};       // reuse the slot for the flipped operator
                  nra = a1; nrb = mkpo(T_OPR, {11'd0, MUT[2] ? s : ~s, op}, pown(dP), here(sP));
                end
              end else begin  // SWI ~ NUM
                if (pval(dQ) == 0) begin
                  n_we = 1'b1; n_wa = sP;
                  n_wd = {pown(dP), MUT[9] ? {a2, ERA_P} : {ERA_P, a2}};    // (a2 *)
                  nra = a1; nrb = mkpo(T_CON, 16'd0, pown(dP), here(sP));
                end else begin
                  logic [SB-1:0] c2;
                  c2 = nf_top[0]; nf_pop = 3'd1;
                  n_we = 1'b1; n_wa = sP;
                  n_wd = {pown(dP), a2, mkp(T_NUM, 16'd0, pval(dQ) - (MUT[3] ? 32'd0 : 32'd1))};   // (#n-1 a2)
                  n_we2 = 1'b1; n_wa2 = c2; n_wd2 = {pown(dP), mkpo(T_CON, 16'd0, pown(dP), here(sP)), ERA_P};  // (* c1)
                  nalloc[c2] <= 1'b1;
                  nra = a1; nrb = mkpo(T_CON, 16'd0, pown(dP), here(c2));
                end
              end
            end
          end else begin
            // binary ~ binary (P on read port 1, Q on read port 2)
            logic anni;
            anni = (tP == tQ) && (plab(dP) == plab(dQ)) && (tP == T_CON || tP == T_DUP);
            if (MUT[4]) anni = (tP == tQ) && (tP == T_CON || tP == T_DUP);
            if (oob(dP)) begin
              tp = 1'b1; tpr = TR_OOB; tpp = dP; fin = 1'b1;
            end else if (oob(dQ)) begin
              tp = 1'b1; tpr = TR_OOB; tpp = dQ; fin = 1'b1;
            end else if (dlP && nforged(nalloc[SB'(pslot(dP))], dP, n_rd)) begin
              tp = 1'b1; tpr = TR_FORGED; tpp = dP; fin = 1'b1;
            end else if (dlQ && nforged(nalloc[SB'(pslot(dQ))], dQ, n_rd2)) begin
              tp = 1'b1; tpr = TR_FORGED; tpp = dQ; fin = 1'b1;
            end else if (dlP && dlQ) begin
              logic [63:0] a1, a2, b1, b2;
              logic [SB-1:0] sP, sQ;
              a1 = n_rd[63:0]; a2 = n_rd[127:64]; b1 = n_rd2[63:0]; b2 = n_rd2[127:64];
              sP = SB'(pslot(dP)); sQ = SB'(pslot(dQ));
              if (!anni && (nf_tot < 2 || vf_tot < 4)) begin
                if (rv_found && can_send) begin
                  // no room for the commutation: PULL protocol (poor -> rich).  The roomy neighbour
                  // re-homes P and sends LINK(Q ~ P') back; Q then migrates with the ordinary NODE rule.
                  snd = 1'b1; sf = {M_PULL, dir_x(rv_dir), dir_y(rv_dir), dQ, a2, a1, dP};
                  nf_push = 3'd1; nf_pd[0] = sP; nalloc[sP] <= 1'b0; mrot <= mrot + 2'd1;
                end else begin pn = 2'd1; pq[0] = {K_LINK, dQ, dP}; st_retry <= st_retry + 1; end
                fin = 1'b1;
              end else if (!anni && (nf_av < 2 || vf_av < 4)) begin
                // wait for the free-slot caches to refill
              end else if (anni) begin
                st_inter <= st_inter + 1;
                nf_push = 3'd2; nf_pd[0] = sP; nf_pd[1] = sQ; nalloc[sP] <= 1'b0; nalloc[sQ] <= 1'b0;
                pn = 2'd1; pq[0] = {K_LINK, b2, a2};
                nra = a1; nrb = (MUT[5] ? b2 : b1);
              end else begin
                logic [SB-1:0] n1, n3, v0, v1, v2, v3;
                logic [63:0] x11, x12, x21, x22;
                logic [3:0] o;
                st_inter <= st_inter + 1;
                o = pown(dP);
                n1 = nf_top[0]; n3 = nf_top[1]; nf_pop = 3'd2;
                v0 = vf_top[0]; v1 = vf_top[1]; v2 = vf_top[2]; v3 = vf_top[3]; vf_pop = 3'd4;
                x11 = mkpo(T_VAR, 16'd0, o, here(v0)); x12 = mkpo(T_VAR, 16'd0, o, here(v1));
                x21 = mkpo(T_VAR, 16'd0, o, here(v2)); x22 = mkpo(T_VAR, 16'd0, o, here(MUT[14] ? v2 : v3));
                n_we = 1'b1; n_wa = sP; n_wd = {o, x12, x11};                       // copy 1 of Q's kind
                n_we2 = 1'b1; n_wa2 = n1; n_wd2 = {o, x22, x21};                     // copy 2 of Q's kind
                wq_a[0] <= sQ; wq_d[0] <= {o, x21, x11};                             // copy 1 of P's kind (queued)
                wq_a[1] <= n3; wq_d[1] <= {o, MUT[6] ? {x12, x22} : {x22, x12}};     // copy 2 of P's kind (queued)
                wq_n <= 2'd2;
                v_we = 1'b1; v_wa = v0; v_wd = {o, 64'd0};                           // owner tags of the fresh vars
                v_we2 = 1'b1; v_wa2 = v1; v_wd2 = {o, 64'd0};
                vq_a[0] <= v2; vq_a[1] <= v3; vq_n <= 2'd2; vq_o <= o;
                nalloc[n1] <= 1'b1; nalloc[n3] <= 1'b1;
                pn = 2'd3;
                pq[0] = {K_LINK, withpay(dQ, here(n1)), a2};
                pq[1] = {K_LINK, withpay(dP, here(sQ)), b1};
                pq[2] = {K_LINK, withpay(dP, here(n3)), b2};
                nra = a1; nrb = withpay(dQ, here(sP)); nst = S_WQ;
              end
            end else if (dlP || dlQ) begin
              // one side local: migrate the local node to the partner's cell (MSG NODE)
              logic [63:0] L, R; logic [131:0] ld;
              L = dlP ? dP : dQ; R = dlP ? dQ : dP; ld = dlP ? n_rd : n_rd2;
              if (can_send) begin
                snd = 1'b1; sf = {M_NODE, px(R), py(R), R, ld[127:64], ld[63:0], L};
                nf_push = 3'd1; nf_pd[0] = SB'(pslot(L)); nalloc[SB'(pslot(L))] <= 1'b0;
              end else begin pn = 2'd1; pq[0] = {K_LINK, dQ, dP}; st_retry <= st_retry + 1; end
              fin = 1'b1;
            end else begin
              if (can_send) begin snd = 1'b1; sf = {M_LINK, px(dP), py(dP), 64'd0, 64'd0, dQ, dP}; end
              else begin pn = 2'd1; pq[0] = {K_LINK, dQ, dP}; end
              fin = 1'b1;
            end
          end
        end

        // ------------------------------------------------------------------ drain queued node / var-tag writes
        S_WQ: begin   // two queued node writes and two var-tag writes, one cycle (both bypassed into the read-ahead)
          if (wq_n != 0) begin n_we = 1'b1; n_wa = wq_a[0]; n_wd = wq_d[0]; end
          if (wq_n > 1 && !MUT[23]) begin n_we2 = 1'b1; n_wa2 = wq_a[1]; n_wd2 = wq_d[1]; end
          if (vq_n != 0) begin v_we = !MUT[24]; v_wa = vq_a[0]; v_wd = {vq_o, 64'd0}; end
          if (vq_n > 1) begin v_we2 = !MUT[24]; v_wa2 = vq_a[1]; v_wd2 = {vq_o, 64'd0}; end
          wq_n <= '0; vq_n <= '0;
          nst = S_LINK;
        end

        // ------------------------------------------------------------------ EXPAND: entries i and i+1 per cycle, allocation alongside
        S_EXN: begin
          logic [7:0] j1;
          logic [SB-1:0] s;
          j1 = ex_i + 8'd1;
          if (ex_e0 && ex_i < ex_nn) begin
            s = nmap[XB'(ex_i)];
            n_we = 1'b1; n_wa = s; n_wd = {MUT[19] ? 4'd0 : ex_own, `TR(rn0[127:64]), `TR(rn0[63:0])};
            nalloc[s] <= 1'b1;
          end
          if (ex_e0 && ex_i < ex_nv) begin
            v_we = 1'b1; v_wa = vmap[XB'(ex_i)]; v_wd = {MUT[19] ? 4'd0 : ex_own, 64'd0};
          end
          if (ex_e0 && ex_i < ex_nr) begin pn = 2'd1; pq[0] = {K_LINK, `TR(rr0[127:64]), `TR(rr0[63:0])}; end
          if (ex_e1 && j1 < ex_nn) begin
            s = nmap[XB'(j1)];
            n_we2 = 1'b1; n_wa2 = s; n_wd2 = {MUT[19] ? 4'd0 : ex_own, `TR(rn1[127:64]), `TR(rn1[63:0])};
            nalloc[s] <= 1'b1;
          end
          if (ex_e1 && j1 < ex_nv) begin
            v_we2 = 1'b1; v_wa2 = MUT[33] ? vmap[XB'(ex_i)] : vmap[XB'(j1)]; v_wd2 = {MUT[19] ? 4'd0 : ex_own, 64'd0};
          end
          if (ex_e1 && j1 < ex_nr) begin pq[pn] = {K_LINK, `TR(rr1[127:64]), `TR(rr1[63:0])}; pn = pn + 2'd1; end
          ex_i <= ex_i + ex_adv;
          if (32'(ex_i) + 32'(ex_adv) >= 32'(ex_lst)) begin
            nra = `TR(ex_root); nrb = ex_x; nst = S_LINK;
          end
          if (ex_in < ex_nn || ex_iv < ex_nv) begin
            alloc = 1'b1; al_nn = ex_nn; al_nv = ex_nv; al_in = ex_in; al_iv = ex_iv;
          end
        end

        default: ;   // S_HALT
      endcase

      // ---- a REF expansion: hand it to a hungry neighbour, or expand here (header read ahead) ----
      if (sp_go) begin
        logic [7:0] nn, nv, nr;
        nn = d_rd[39:32]; nv = d_rd[47:40]; nr = d_rd[55:48];
        hrot <= hrot + 2'd1;
        if (!sp_local_only && hv_found && can_send && !MUT[7]) begin
          snd = 1'b1; sf = {M_SPAWN, dir_x(hv_dir), dir_y(hv_dir), 64'd0, 64'd0, sp_x_p, sp_ref_p};
          fin = 1'b1;
        end else if ((SB+2)'(nn) <= nf_tot && (SB+2)'(nv) <= vf_tot && (32'(tq_tot) + 32'(nr) + 1) < QDEPTH) begin
          ex_nbase <= d_rd[15:0]; ex_rbase <= d_rd[31:16]; ex_root <= d_rd[127:64];
          ex_nn <= nn; ex_nv <= nv; ex_nr <= nr; ex_own <= pown(sp_ref_p); ex_x <= sp_x_p;
          ex_ref <= plab(sp_ref_p);
          alloc = 1'b1; al_start = 1'b1; al_nn = nn; al_nv = nv; al_in = '0; al_iv = '0;   // first allocation batch now
          if (!MUT[31]) bufok <= 1'b0;                                      // new definition: drop the buffered pair
        end else if (NT > 1) begin
          // not enough room here: forward the SPAWN to a neighbour
          logic [2:0] t;
          logic [3:0] fx, fy;
          t = (rr == 3'd0) ? 3'd1 : rr;
          fx = tx[t]; fy = ty[t];
          if (rv_found) begin fx = dir_x(rv_dir); fy = dir_y(rv_dir); mrot <= mrot + 2'd1; end   // prefer a roomy neighbour
          else rr <= (t == 3'(NT - 1)) ? 3'd0 : t + 1;
          st_retry <= st_retry + 1;
          if (can_send) begin snd = 1'b1; sf = {M_SPAWN, fx, fy, 64'd0, 64'd0, sp_x_p, sp_ref_p}; end
          else begin pn = 2'd1; pq[0] = {K_SPAWN, sp_x_p, sp_ref_p}; end
          fin = 1'b1;
        end else begin
          err <= 4'd2; nst = S_HALT;    // out of memory on a 1x1 fabric
        end
      end

      // ---- map allocation: up to 4 node slots and 4 var slots per cycle from the stack caches ----
      if (alloc) begin
        logic [7:0] in2, iv2;
        al_kn = 4'd0; al_kv = 4'd0;
        for (int j = 0; j < 8; j++) begin
          if (32'(al_in) + j < 32'(al_nn) && j < 32'(nf_av)) begin nmap[XB'(32'(al_in) + j)] <= nf_top[j]; al_kn = 4'(j + 1); end
          if (32'(al_iv) + j < 32'(al_nv) && j < 32'(vf_av)) begin vmap[XB'(32'(al_iv) + j)] <= vf_top[j]; al_kv = 4'(j + 1); end
        end
        nf_pop = al_kn - 4'(MUT[25] && al_kn > 4'd1); vf_pop = al_kv;
        in2 = al_in + 8'(al_kn); iv2 = al_iv + 8'(al_kv);
        ex_in <= in2; ex_iv <= iv2;
        if (al_start) begin ex_i <= 8'd0; nst = S_EXN; end
      end

      // ---- hand the continuation link to the VHU (it follows the var chain; main picks new work) ----
      if (!fin && nst == S_LINK && !nrsp && !nrsx && !nrfw && !tp && !vh_v && !MUT[37]) begin
        logic [63:0] hA, hB;
        hA = ordA(nra, nrb); hB = ordB(nra, nrb);
        if (is_var(hA) && !oob(hA) && local_p(hA) && !xown(hA, hB)) begin
          hand = 1'b1; nvh_v = 1'b1; nvh_a = hA; nvh_b = hB; fin = 1'b1;
        end
      end

      // ---- VHU: one var exchange per cycle (write port 2, read port 2) ----
      if (vh_v && !vh_ov) begin
        logic conflict;
        logic [63:0] old, A2, B2;
        conflict = (state == S_LINK && dvar && local_p(A) && pslot(A) == pslot(vh_a) && !MUT[35]) || v_we2 ||
                   32'(vf_room) < 32'(vf_push) + 1;        // room in the free-var cache for its push
        if (!conflict) begin
          vh_go = 1'b1;
          st_vhu <= st_vhu + 1;
          old = v_rd2[63:0];
          if (v_rd2[67:64] != pown(vh_a) && !MUT[16]) begin
            vh_ov <= 1'b1; vh_oa <= vh_a; vh_ob <= vh_b;          // forged: the main engine traps it
          end else if (ptag(old) == T_NONE) begin
            v_we2 = 1'b1; v_wa2 = SB'(pslot(vh_a)); v_wd2 = {v_rd2[67:64], vh_b};
            nvh_v = 1'b0;
          end else begin
            v_we2 = 1'b1; v_wa2 = SB'(pslot(vh_a)); v_wd2 = {OWN_FREE, 64'd0};
            vf_pd[vf_push[0]] = SB'(pslot(vh_a)); vf_push = vf_push + 3'd1;
            A2 = ordA(old, vh_b); B2 = ordB(old, vh_b);
            if (is_var(A2) && !oob(A2) && local_p(A2) && !xown(A2, B2)) begin nvh_a = A2; nvh_b = B2; end
            else begin vh_ov <= 1'b1; vh_oa <= old; vh_ob <= vh_b; end   // redex / remote / check: back to main
          end
        end
      end

      // ---- the step finished: pick the next task or message in the same cycle (no IDLE cycle) ----
      if (fin && nst != S_HALT) begin
        logic msg_ok, pick_msg;
        msg_ok = ej_v && !ej_taken && !((ej_f.kind == M_NODE || ej_f.kind == M_PULL) && (nf_av == 0 || n_we || nf_pop != 0));
        pick_msg = msg_ok && (!q_ok || !can_send || rnd_msg);
        nst = S_IDLE; nrsp = 1'b0; nrsx = 1'b0; nrfw = 1'b0;
        if (stall_now) begin
          // verification knob: skip a cycle
        end else if (vh_ov && !MUT[36]) begin
          // the VHU's hand-back first (frees the VHU)
          st_tasks <= st_tasks + 1;
          nra = vh_oa; nrb = vh_ob; nst = S_LINK;
          vh_ov <= 1'b0; nvh_v = 1'b0;
        end else if (pick_msg) begin
          st_tasks <= st_tasks + 1;
          ej_taken <= 1'b1;
          case (ej_f.kind)
            M_LINK: begin nra = ej_f.p0; nrb = ej_f.p1; nst = S_LINK; end
            M_SPAWN: begin nra = ej_f.p0; nrb = ej_f.p1; nrsx = 1'b1; nst = S_LINK; end
            default: begin   // M_NODE / M_PULL: re-home the travelling node, then link it with its partner
                             // (PULL: forward the link to the partner's cell instead, rfw)
              logic [SB-1:0] s;
              if (xown(ej_f.p0, ej_f.p3)) begin tp = 1'b1; tpr = TR_CROSS; tpp = lowown(ej_f.p0, ej_f.p3); end
              else begin
                s = nf_top[0]; nf_pop = 3'd1;
                n_we = 1'b1; n_wa = s;
                n_wd = {pown(ej_f.p0), MUT[10] ? {ej_f.p1, ej_f.p2} : {ej_f.p2, ej_f.p1}};
                nalloc[s] <= 1'b1;
                nra = withpay(ej_f.p0, here(s)); nrb = ej_f.p3; nst = S_LINK;
                if (ej_f.kind == M_PULL) begin nra = ej_f.p3; nrb = withpay(ej_f.p0, here(s)); nrfw = 1'b1; end
              end
            end
          endcase
        end else if (q_ok) begin
          logic [129:0] e;
          st_tasks <= st_tasks + 1;
          e = tq_top; tq_pop = 3'd1;
          nra = e[63:0]; nrb = e[127:64]; nrsp = (e[129:128] == K_SPAWN); nrfw = (e[129:128] == K_FWD); nst = S_LINK;
        end
      end

      // ---- apply side effects ----
      if (tp) begin
        st_traps <= st_traps + 1;
        tr_mask[(32'(tpr) - 1) * 16 + 32'(pown(tpp))] <= 1'b1;
        if (st_traps == 0) begin tr_reason <= tpr; tr_owner <= pown(tpp); tr_addr <= pval(tpp); end
      end
      tq_push = 3'(pn); tq_pd = pq;
      if (pn != 0) begin
        if (32'(tq_tot) + 32'(pn) > QDEPTH) begin err <= 4'd1; nst = S_HALT; tq_push = '0; end
        else if (32'(tq_tot) + 32'(pn) > st_maxq) st_maxq <= 32'(tq_tot) + 32'(pn);
      end
      begin
        logic pop;
        pop = l_pop && ob_cnt != 0;
        if (snd) begin
          ob[OB'(ob_hd + OB'(ob_cnt))] <= sf;
          case (sf.kind) M_LINK: st_msg0 <= st_msg0 + 1; M_NODE, M_PULL: st_msg1 <= st_msg1 + 1; default: st_msg2 <= st_msg2 + 1; endcase
        end
        if (pop) ob_hd <= ob_hd + 1'b1;
        ob_cnt <= ob_cnt + (OB+1)'(snd) - (OB+1)'(pop);
      end
      state <= nst; ra <= nra; rb <= nrb; rsp <= nrsp; rsx <= nrsx; rfw <= nrfw;
      vh_v <= nvh_v; vh_a <= nvh_a; vh_b <= nvh_b;

      // ---- memory writes: one write port per array ----
      if (n_we) node_mem[n_wa] <= n_wd;
      if (n_we2) node_mem[n_wa2] <= n_wd2;
      if (v_we) var_mem[v_wa] <= v_wd;
      if (v_we2) var_mem[v_wa2] <= v_wd2;

      // ---- stack caches: pops, pushes, refill arrival, spill / refill (one SRAM access each per cycle) ----
      `CSTACK(nc, ncnt, nsp, npend, nstk, nstk_rd, NK, 10, 7, nf_pop, nf_push, nf_pd, 2, SLOTS, SB, SB, nc_n)
      `CSTACK(vc, vcnt, vsp, vpend, vstk, vstk_rd, VK, 10, 7, vf_pop, vf_push, vf_pd, 2, SLOTS, SB, SB, vc_n)
      `CSTACK(qc, qcnt, qsp, qpend, tqm, tqm_rd, QK, 5, 2, tq_pop, tq_push, tq_pd, 3, QDEPTH, 130, QB, qc_n)

      // ---- read-ahead: the addresses the NEXT cycle's step needs (synchronous reads, write bypass) ----
      la_A = ordA(nra, nrb); la_B = ordB(nra, nrb);
      if (qfirst(la_A, la_B)) begin la_P = la_B; la_Q = la_A; end else begin la_P = la_A; la_Q = la_B; end
      la_v = SB'(pslot(la_A)); la_n1 = SB'(pslot(la_P)); la_n2 = SB'(pslot(la_Q));
      la_d = DB'(plab(la_Q));
      v_rd   <= (v_we2 && v_wa2 == la_v) ? v_wd2 : (v_we && v_wa == la_v) ? v_wd : var_mem[la_v];
      la_v2 = SB'(pslot(nvh_a));
      v_rd2  <= (v_we2 && v_wa2 == la_v2) ? v_wd2 : (v_we && v_wa == la_v2 && !MUT[38]) ? v_wd : var_mem[la_v2];
      n_rd   <= (n_we2 && n_wa2 == la_n1 && !MUT[32]) ? n_wd2 : (n_we && n_wa == la_n1 && !MUT[22]) ? n_wd : node_mem[la_n1];
      n_rd2  <= (n_we2 && n_wa2 == la_n2) ? n_wd2 : (n_we && n_wa == la_n2) ? n_wd : node_mem[la_n2];
      d_rd   <= dirm[la_d];
      rom_v  <= rom_req && rom_gnt; rvp <= rom_q;
    end
    if (cfg_we && cfg_sel == 2'd2) dirm[DB'(cfg_a)] <= cfg_d;
  end

`ifndef SYNTHESIS
  // ---------------- debug trace (+trace) ----------------
  bit trace_on;
  initial trace_on = $test$plusargs("trace");
  always @(posedge clk) if (trace_on && !rst && state != S_INIT)
    $display("c%0d,%0d st=%0d ra=%h rb=%h sp=%0d%0d q=%0d/%0d nf=%0d vf=%0d inter=%0d", X, Y, state, ra, rb, rsp, rsx, qcnt, qsp, nf_tot, vf_tot, st_inter);
  // ---------------- dump (testbench) ----------------
  always @(posedge clk) begin
    if (dump) begin
      int fd;
      for (int i = 0; i < SLOTS; i++) na_out[i] = nalloc[i];
      $writememh($sformatf("%s/out_nalloc_%0d_%0d.hex", outdir, X, Y), na_out);
      $writememh($sformatf("%s/out_node_%0d_%0d.hex", outdir, X, Y), node_mem);
      $writememh($sformatf("%s/out_var_%0d_%0d.hex", outdir, X, Y), var_mem);
      fd = $fopen($sformatf("%s/out_stats_%0d_%0d.txt", outdir, X, Y), "w");
      $fwrite(fd, "cycles %0d\ninteractions %0d\nbusy %0d\ntasks %0d\nlinks %0d\nretry %0d\nmsg_link %0d\nmsg_node %0d\nmsg_spawn %0d\nmaxq %0d\nfree_nodes %0d\nfree_vars %0d\nerr %0d\npeak_nodes %0d\npeak_vars %0d\nvhu %0d\ntraps %0d\ntrap_reason %0d\ntrap_owner %0d\ntrap_addr %0d\ntrap_mask %0d\n",
              cyc, st_inter, st_busy, st_tasks, st_links, st_retry, st_msg0, st_msg1, st_msg2, st_maxq, nf_tot, vf_tot, err, SLOTS - st_minfn, SLOTS - st_minfv, st_vhu, st_traps, tr_reason, tr_owner, tr_addr, tr_mask);
      $fclose(fd);
    end
  end
`endif
endmodule
