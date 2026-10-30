source ~/env.sh
cd /workspace/work/omega
ulimit -v 4500000
export PYTHONPATH=.:tests OMEGA_JOBS=1 OMEGA_SPLIT=800
python3 results/s19/diag_rtl.py treesum 7 8 8 16 400000 > results/s19/diag_fwd_ts7_s16.txt 2>&1
python3 results/s19/diag_rtl.py treesum 7 8 8 18 400000 > results/s19/diag_fwd_ts7_s18.txt 2>&1
echo ALLDONE >> results/s19/rtl12.err
