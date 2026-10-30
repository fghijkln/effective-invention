source ~/env.sh
cd /workspace/work/omega
while ! grep -q DONE results/s19/sweep7.jsonl 2>/dev/null; do sleep 20; done
ulimit -v 4500000
export PYTHONPATH=.:tests OMEGA_JOBS=1 OMEGA_SPLIT=800
# step 19 final RTL (rgrad=3 with reserve + full-cell pass-on): redo every rgrad=3 run
OMEGA_RTO=8 OMEGA_RGRAD=3 python3 results/s19/rtl_big.py 1 30 7 >> results/s19/rtl_fwd.jsonl 2>>results/s19/rtl13.err
OMEGA_RTO=8 OMEGA_RGRAD=3 python3 results/s19/rtl_big.py 1 13 5 6 0 1 2 3 4 >> results/s19/rtl_fwd.jsonl 2>>results/s19/rtl13.err
echo DONE >> results/s19/rtl_fwd.jsonl
OMEGA_RTO=8 OMEGA_RGRAD=3 OMEGA_XARGS="rgrad=3 rsv4 fwd" python3 results/s19/rtl_ts9.py 1 30 >> results/s19/rtl_ts9_fwd.jsonl 2>>results/s19/rtl13.err
# rgrad=0 must still be step 18 cycle for cycle
OMEGA_RTO=32 OMEGA_RGRAD=0 python3 bench/rto18_rtl.py 3 > results/s19/rto_global_old2.jsonl 2>>results/s19/rtl13.err
echo ALLDONE >> results/s19/rtl13.err
