Designs (synth/out/*/summary.json): omega_cell std cell 150,915 µm² + memory 348,558 µm² (391,168 bits), Fmax 35.0 MHz; omega_rom (4 cells) std cell 2,501 µm² + memory 628,386 µm² (786,432 bits), Fmax 1304 MHz; tx_core std cell 166,993 µm² + memory 28,450 µm² (26,976 bits), Fmax 95.5 MHz. Omega cycles: results/bench_c2x2p1.json.

| machine | cells + ROMs | area mm² (std cell / memory) | per cell mm² | Fmax MHz | fib(20) cycles | time µs | area × cycles (vs T-128) | std-cell area × cycles (vs T-128) | area × time (vs T-128) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| TACHYON-128 tx_core (v6 cycles) | 1 + 0 | 0.195 (0.167 / 0.028) | 0.195 | 95.5 | 296,931 | 3,110 (1.00×) | 1.00× | 1.00× | 1.00× |
| TACHYON-Omega 1x1 | 1 + 1 | 1.130 (0.153 / 0.977) | 1.130 | 35.0 | 1,006,974 | 28,783 (9.25×) | 19.61× | 3.12× | 53.52× |
| TACHYON-Omega 2x2 | 4 + 1 | 2.629 (0.606 / 2.023) | 0.657 | 35.0 | 269,881 | 7,714 (2.48×) | 12.23× | 3.30× | 33.36× |
| TACHYON-Omega 4x4 | 16 + 4 | 10.515 (2.425 / 8.090) | 0.657 | 35.0 | 70,938 | 2,028 (0.65×) | 12.85× | 3.47× | 35.07× |
| TACHYON-Omega 8x8 | 64 + 16 | 42.060 (9.699 / 32.362) | 0.657 | 35.0 | 25,635 | 733 (0.24×) | 18.58× | 5.01× | 50.70× |
