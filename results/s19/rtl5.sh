source ~/env.sh
cd /workspace/work/omega
while ! grep -q DONE results/s19/rto_global_g3.jsonl 2>/dev/null; do sleep 20; done
ulimit -v 4500000
export PYTHONPATH=.:tests OMEGA_JOBS=1 OMEGA_SPLIT=800
G=results/s19/rto_global_old.jsonl
OMEGA_RTO=32 OMEGA_RGRAD=0 python3 bench/rto18_rtl.py 3 >> $G 2>>results/s19/rtl5.err
echo DONE >> $G
