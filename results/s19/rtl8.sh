source ~/env.sh
cd /workspace/work/omega
ulimit -v 4500000
export PYTHONPATH=.:tests OMEGA_JOBS=1 OMEGA_SPLIT=800
O=results/s19/rtl_rsv.jsonl
OMEGA_RTO=8 OMEGA_RGRAD=3 python3 results/s19/rtl_big.py 1 13 7 >> $O 2>>results/s19/rtl8.err
OMEGA_RTO=8 OMEGA_RGRAD=3 OMEGA_XARGS="rgrad=3 rsv4" python3 results/s19/rtl_ts9.py 1 30 >> results/s19/rtl_ts9_rsv.jsonl 2>>results/s19/rtl8.err
OMEGA_RTO=8 OMEGA_RGRAD=3 python3 results/s19/rtl_big.py 1 13 0 1 2 3 4 5 6 >> $O 2>>results/s19/rtl8.err
echo DONE >> $O
