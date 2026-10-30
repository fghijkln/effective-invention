source ~/env.sh
cd /workspace/work/omega
while ! grep -q DONE results/s19/rto_global_old.jsonl 2>/dev/null; do sleep 20; done
ulimit -v 4500000
export PYTHONPATH=.:tests OMEGA_JOBS=1 OMEGA_SPLIT=800
O=results/s19/rtl_big.jsonl
for cfg in "8 3" "8 0" "32 0"; do set -- $cfg
  OMEGA_RTO=$1 OMEGA_RGRAD=$2 python3 results/s19/rtl_big.py 4 13 2 5 6 7 >> $O 2>>results/s19/rtl6.err
done
echo DONE >> $O
