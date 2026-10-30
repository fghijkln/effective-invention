source ~/env.sh
cd /workspace/work/omega
while ! grep -q DONE results/s19/rto_global_g.jsonl 2>/dev/null; do sleep 20; done
ulimit -v 4500000
export PYTHONPATH=.:tests OMEGA_JOBS=1 OMEGA_SPLIT=800
OMEGA_RTO=8 OMEGA_RGRAD=3 OMEGA_XARGS="rgrad=3" python3 results/s19/rtl_ts9.py 1 30 >> results/s19/rtl_ts9.jsonl 2>>results/s19/rtl4.err
G=results/s19/rto_global_g3.jsonl
OMEGA_RTO=8 OMEGA_RGRAD=3 python3 bench/rto18_rtl.py 3 >> $G 2>>results/s19/rtl4.err
echo DONE >> $G
