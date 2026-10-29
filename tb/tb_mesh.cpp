// Verilator testbench: reset, run until the quiescence line is high for 2 cycles, dump, report.
#include "Vomega_mesh.h"
#include "verilated.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>

int main(int argc, char** argv) {
    Verilated::commandArgs(argc, argv);
    auto* m = new Vomega_mesh;
    unsigned long long maxc = 50000000ULL;
    unsigned seed = 1, jit = 0, stl = 0, pmsg = 128, fi = 0, spk = 16, sph = 1, ll = 1, spk2 = 4, spkp = 4, govb = 30;
    for (int i = 1; i < argc; i++) {
        if (!strncmp(argv[i], "+seed=", 6)) seed = strtoul(argv[i] + 6, 0, 0);
        if (!strncmp(argv[i], "+jitter=", 8)) jit = strtoul(argv[i] + 8, 0, 0);
        if (!strncmp(argv[i], "+stall=", 7)) stl = strtoul(argv[i] + 7, 0, 0);
        if (!strncmp(argv[i], "+fi=", 4)) fi = strtoul(argv[i] + 4, 0, 0);
        if (!strncmp(argv[i], "+spawnk=", 8)) spk = strtoul(argv[i] + 8, 0, 0);
        if (!strncmp(argv[i], "+spawnhint=", 11)) sph = strtoul(argv[i] + 11, 0, 0);
        if (!strncmp(argv[i], "+spawnk2=", 9)) spk2 = strtoul(argv[i] + 9, 0, 0);
        if (!strncmp(argv[i], "+spawnkp=", 9)) spkp = strtoul(argv[i] + 9, 0, 0);
        if (!strncmp(argv[i], "+govb=", 6)) govb = strtoul(argv[i] + 6, 0, 0);
        if (!strncmp(argv[i], "+linklocal=", 11)) ll = strtoul(argv[i] + 11, 0, 0);
        if (!strncmp(argv[i], "+pmsg=", 6)) pmsg = strtoul(argv[i] + 6, 0, 0);
        if (!strncmp(argv[i], "+maxcycles=", 11)) maxc = strtoull(argv[i] + 11, 0, 0);
    }
    m->seed = seed; m->jitter = jit; m->stall = stl; m->pmsg = pmsg; m->fi = fi; m->spawn_k = spk; m->spawn_hint = sph; m->link_local = ll; m->spawn_k2 = spk2; m->spawn_kp = spkp; m->gov_b = govb; m->dump = 0;
    m->rst = 1; m->clk = 0;
    for (int i = 0; i < 4; i++) { m->clk = 1; m->eval(); m->clk = 0; m->eval(); }
    m->rst = 0;
    // initialisation (free-stack build) is not counted
    unsigned long long init = 0;
    while (!m->all_ready) { m->clk = 1; m->eval(); m->clk = 0; m->eval(); init++; }
    unsigned long long cyc = 0; int quiet = 0; int status = 0;
    while (true) {
        m->clk = 1; m->eval(); m->clk = 0; m->eval(); cyc++;
        if (m->any_err) { status = 2; break; }
        quiet = m->all_idle ? quiet + 1 : 0;
        if (quiet >= 2) break;
        if (cyc >= maxc) { status = 3; break; }
    }
    m->dump = 1; m->clk = 1; m->eval(); m->clk = 0; m->eval(); m->dump = 0;
    printf("status %d\ncycles %llu\ninteractions %u\nerr %u\ninit %llu\n", status, cyc - 2 + (status ? 2 : 0), m->interactions, m->any_err, init);
    m->final();
    delete m;
    return 0;
}
