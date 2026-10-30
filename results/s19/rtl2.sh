source ~/env.sh
cd /workspace/work/omega
ulimit -v 4500000
export PYTHONPATH=.:tests OMEGA_JOBS=1 OMEGA_SPLIT=800
O=results/s19/rtl_ts9.jsonl
for cfg in "32 0" "8 0" "8 7"; do set -- $cfg
  OMEGA_RTO=$1 OMEGA_RGRAD=$2 OMEGA_XARGS="rgrad=$2" python3 results/s19/rtl_ts9.py 1 10 >> $O 2>>results/s19/rtl2.err
done
echo DONE >> $O
