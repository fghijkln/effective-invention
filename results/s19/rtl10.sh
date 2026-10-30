source ~/env.sh
cd /workspace/work/omega
ulimit -v 4500000
export PYTHONPATH=.:tests OMEGA_JOBS=1 OMEGA_SPLIT=800
OMEGA_RTO=8 OMEGA_RGRAD=3 python3 results/s19/rtl_big.py 1 13 5 6 >> results/s19/rtl_rsv.jsonl 2>>results/s19/rtl10.err
echo DONE >> results/s19/rtl_rsv.jsonl
for cfg in "8 3" "8 0" "32 0"; do set -- $cfg
  OMEGA_RTO=$1 OMEGA_RGRAD=$2 python3 results/s19/rtl_big.py 14 30 7 >> results/s19/rtl_ts7.jsonl 2>>results/s19/rtl10.err
done
echo DONE >> results/s19/rtl_ts7.jsonl
echo ALLDONE >> results/s19/rtl10.err
