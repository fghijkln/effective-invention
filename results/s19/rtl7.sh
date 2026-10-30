source ~/env.sh
cd /workspace/work/omega
while ! grep -q DONE results/s19/rtl_big.jsonl 2>/dev/null; do sleep 20; done
ulimit -v 4500000
export PYTHONPATH=.:tests OMEGA_JOBS=1 OMEGA_SPLIT=800
OMEGA_RTO=8 OMEGA_RGRAD=7 python3 results/s19/diag_rtl.py treesum 7 8 8 3 300000 > results/s19/diag_g7_ts7.txt 2>&1
echo DONE >> results/s19/diag_g7_ts7.txt
