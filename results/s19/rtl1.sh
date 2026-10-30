cd /workspace/work/omega
ulimit -v 4500000
export PYTHONPATH=.:tests OMEGA_JOBS=1
O=results/s19/rtl_ts9.jsonl
OMEGA_RTO=32 python3 results/s19/rtl_ts9.py 1 10 >> $O 2>>results/s19/rtl1.err
OMEGA_RTO=8 python3 results/s19/rtl_ts9.py 1 10 >> $O 2>>results/s19/rtl1.err
echo DONE >> $O
