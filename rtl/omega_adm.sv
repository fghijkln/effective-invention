// TACHYON-Omega step 26 (SPEC 7.5): memory-bound admission control in hardware.
// A small controller beside the mesh holds a job table (owner, typed, reservation (n, v), the REF of the job's
// @main) and a FIFO head.  It starts a job only while, for nodes and vars alike,
//     reserved (sum over running Omega-L jobs) + its own  <=  budget  (= slots - margin, given by the host),
// at most one job per owner, and one root var slot of a small pool (RR slots of cell (0,0), outside the free
// stacks) is free.  A start is two host-port actions on cell (0,0): write {owner, NONE} into the root slot,
// then hand the cell the task {REF @main, VAR root}, which it takes as a SPAWN (expand here or hand on), so the
// cell's own allocator places @main.  An Omega-L job whose bound exceeds the budget is rejected when it reaches
// the head; an untyped job passes unreserved (in FIFO order, one per owner).
// Completion is detected at mesh quiescence (every cell idle for 2 cycles): then no task, message, retry or
// var-hop link of any owner exists, so every running job is done; the controller reads each root from its shadow
// copy (it watches cell (0,0)'s var writes), releases the reservation and frees the root slot when the result is
// an atom (NUM / ERA); a data result stays in the fabric (no host unload in RTL): its root slot stays used and,
// for an Omega-L job, its reservation stays charged.  Run-time knob adm_on (+adm, default 0): with adm_on = 0
// every output is idle and the mesh is cycle for cycle the step-25 mesh.
`include "omega_defs.svh"
module omega_adm #(
  parameter int NJ = 512, parameter int RR = 16, parameter int NCELL = 1,
  parameter logic [511:0] MUT = '0
) (
  input  logic        clk, rst, adm_on, ready, cells_idle,
  input  logic        mon_we, mon_we2,
  input  logic [11:0] mon_wa, mon_wa2,
  input  logic [63:0] mon_wd, mon_wd2,
  output logic        hq_v,
  output logic [63:0] hq_a, hq_b,
  input  logic        hq_ack,
  output logic        hw_v,
  output logic [11:0] hw_a,
  output logic [67:0] hw_d,
  input  logic        hw_ack,
  output logic [11:0] rbase,
  input  logic [31:0] sum_free_n, sum_free_v, min_free,   // audit (simulation)
  output logic        adm_idle,
  output logic [3:0]  adm_err
);
  `include "omega_funcs.svh"
  localparam int JB = $clog2(NJ) + 1, KB = $clog2(RR);
  logic [63:0] jinfo [NJ];     // {need_v[23:0], need_n[23:0], 11'0, typed, owner[3:0]}
  logic [63:0] jref  [NJ];     // REF @main of the job, stamped with its owner
  logic [31:0] cfg [8];        // njobs, budget_n, budget_v, root base slot, margin, total free slots, -, -
`ifndef SYNTHESIS
  initial begin
    int a; string imgdir;
    for (int i = 0; i < 8; i++) cfg[i] = '0;
    if ($value$plusargs("adm=%d", a) && a != 0) begin
      if (!$value$plusargs("img=%s", imgdir)) imgdir = "build/img";
      $readmemh($sformatf("%s/adm_cfg.hex", imgdir), cfg);
      $readmemh($sformatf("%s/adm_info.hex", imgdir), jinfo);
      $readmemh($sformatf("%s/adm_ref.hex", imgdir), jref);
    end
  end
`endif

  logic [JB-1:0] head;
  logic [RR-1:0] s_run, s_used;
  logic [RR-1:0][JB-1:0] s_job;
  logic [RR-1:0][63:0]   rootw;
  logic [15:0]   own_busy;
  logic [23:0]   res_n, res_v;
  logic [1:0]    pend;          // 1: root reset write pending, 2: start task pending
  logic [1:0]    idle_cnt;
  logic          comp;          // completion sweep over the root slots
  logic [KB:0]   ci;
  logic [31:0]   cyc, nviol, untyped_run;
  logic          ret_untyped, ended;
  logic [31:0]   pk_n, pk_v, mx_rn, mx_rv;
  logic [63:0]   hd_info;
  logic          hd_typed, hd_rej, hd_fit, hs_found;
  logic [3:0]    hd_own;
  logic [23:0]   hd_n, hd_v;
  logic [KB-1:0] hs;

  always_comb begin
    hd_info = jinfo[head[JB-2:0]];
    hd_own = hd_info[3:0]; hd_typed = hd_info[4];
    hd_n = hd_info[39:16]; hd_v = hd_info[63:40];
    hd_rej = hd_typed && (32'(hd_n) > cfg[1] || 32'(hd_v) > cfg[2]) && !MUT[61];      // mutant 61: no reject check
    hd_fit = !hd_typed || (MUT[60] ? (32'(hd_n) <= cfg[1] && 32'(hd_v) <= cfg[2])     // mutant 60: ignores running jobs
                                   : (32'(res_n) + 32'(hd_n) <= cfg[1] && 32'(res_v) + 32'(hd_v) <= cfg[2]));
    hs_found = 1'b0; hs = '0;
    for (int k = RR - 1; k >= 0; k--) if (!s_used[k]) begin hs_found = 1'b1; hs = KB'(k); end
    rbase = 12'(cfg[3]);
    hq_v = adm_on && pend == 2'd2 && !hq_ack;
    hw_v = adm_on && pend == 2'd1 && !hw_ack;
    adm_idle = !adm_on || (adm_err != 0) || (32'(head) >= cfg[0] && pend == 2'd0 && s_run == '0 && !comp);
  end

  always_ff @(posedge clk) begin
    if (rst) begin
      head <= '0; s_run <= '0; s_used <= '0; own_busy <= '0; res_n <= '0; res_v <= '0; pend <= '0;
      idle_cnt <= '0; comp <= 1'b0; ci <= '0; cyc <= '0; nviol <= '0; untyped_run <= '0; ret_untyped <= 1'b0;
      ended <= 1'b0; adm_err <= '0; pk_n <= '0; pk_v <= '0; mx_rn <= '0; mx_rv <= '0;
      hq_a <= '0; hq_b <= '0; hw_a <= '0; hw_d <= '0;
    end else if (adm_on && ready && adm_err == 0) begin
      cyc <= cyc + 1;
      // shadow copies of the root slots (cell (0,0) var writes, registered there)
      if (mon_we && mon_wa >= 12'(cfg[3]) && 32'(mon_wa) < cfg[3] + RR) rootw[KB'(32'(mon_wa) - cfg[3])] <= mon_wd;
      if (mon_we2 && mon_wa2 >= 12'(cfg[3]) && 32'(mon_wa2) < cfg[3] + RR) rootw[KB'(32'(mon_wa2) - cfg[3])] <= mon_wd2;
      idle_cnt <= (cells_idle && pend == 2'd0) ? ((idle_cnt == 2'd3) ? idle_cnt : idle_cnt + 2'd1) : 2'd0;
      if (pend == 2'd1) begin
        if (hw_ack) pend <= 2'd2;
      end else if (pend == 2'd2) begin
        if (hq_ack) pend <= 2'd0;
      end else if (comp) begin
        // completion sweep: one root slot per cycle
        if (s_run[KB'(ci)]) begin
          logic [63:0] w, inf;
          logic atom;
          w = rootw[KB'(ci)]; inf = jinfo[s_job[KB'(ci)][JB-2:0]];
          atom = ptag(w) == T_NUM || ptag(w) == T_ERA;
          $display("adm done %0d %0d %0d %h", s_job[KB'(ci)], cyc, ci, w);
          s_run[KB'(ci)] <= 1'b0; own_busy[inf[3:0]] <= 1'b0;
          if (!inf[4]) untyped_run <= untyped_run - 1;
          if (atom) begin
            s_used[KB'(ci)] <= 1'b0;
            if (inf[4] && !MUT[64]) begin res_n <= res_n - inf[39:16]; res_v <= res_v - inf[63:40]; end   // mutant 64: never released
          end else if (!inf[4]) ret_untyped <= 1'b1;
        end
        if (32'(ci) == RR - 1) comp <= 1'b0;
        ci <= ci + 1'b1;
      end else if (idle_cnt >= 2'd2 && s_run != '0) begin
        comp <= 1'b1; ci <= '0;
      end else if (32'(head) < cfg[0]) begin
        if (hd_rej) begin
          $display("adm reject %0d %0d", head, cyc);
          head <= head + 1'b1;
        end else if ((!own_busy[hd_own] || MUT[62]) && hs_found && hd_fit) begin    // mutant 62: owners overlap
          $display("adm start %0d %0d %0d", head, cyc, hs);
          s_used[hs] <= 1'b1; s_run[hs] <= 1'b1; s_job[hs] <= head; own_busy[hd_own] <= 1'b1;
          if (hd_typed) begin res_n <= res_n + hd_n; res_v <= res_v + hd_v; end
          else untyped_run <= untyped_run + 1;
          hw_a <= 12'(cfg[3] + 32'(hs)); hw_d <= {hd_own, 64'd0};
          hq_a <= jref[head[JB-2:0]]; hq_b <= mkpo(T_VAR, 16'd0, hd_own, mkaddr(4'd0, 4'd0, 12'(cfg[3] + 32'(hs))));
          pend <= MUT[63] ? 2'd2 : 2'd1;                                               // mutant 63: no root reset
          head <= head + 1'b1;
        end else if (s_run == '0 && idle_cnt >= 2'd2) begin
          $display("adm blocked %0d %0d", head, cyc);
          adm_err <= 4'd1;
        end
      end
      // audit (simulation): live <= reserved while no untyped job runs or left data behind, reserved <= budget,
      // and on a mesh every cell keeps the margin free
      begin
        logic [31:0] ln, lv;
        ln = cfg[5] - sum_free_n; lv = cfg[5] - sum_free_v;
        if (ln > pk_n) pk_n <= ln;
        if (lv > pk_v) pk_v <= lv;
        if (32'(res_n) > mx_rn) mx_rn <= 32'(res_n);
        if (32'(res_v) > mx_rv) mx_rv <= 32'(res_v);
        if ((untyped_run == 0 && !ret_untyped && (ln > 32'(res_n) || lv > 32'(res_v))) ||
            32'(res_n) > cfg[1] || 32'(res_v) > cfg[2] || (NCELL > 1 && min_free < cfg[4])) begin
          if (nviol == 0) $display("adm viol %0d %0d %0d %0d %0d %0d", cyc, ln, lv, res_n, res_v, min_free);
          nviol <= nviol + 1;
        end
      end
    end
    if (!rst && adm_on && adm_idle && !ended) begin
      ended <= 1'b1;
      $display("adm end %0d %0d %0d %0d %0d %0d %0d", cyc, pk_n, pk_v, mx_rn, mx_rv, nviol, adm_err);
    end
  end
endmodule
