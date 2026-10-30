source ~/env.sh
cd /workspace/work/omega
while ! grep -q ALLDONE results/s19/rtl10.err 2>/dev/null; do sleep 20; done
ulimit -v 4500000
export PYTHONPATH=.:tests OMEGA_JOBS=1 OMEGA_SPLIT=800
for cfg in "8 0" "32 0"; do set -- $cfg
  OMEGA_RTO=$1 OMEGA_RGRAD=$2 python3 results/s19/rtl_big.py 4 13 0 1 3 4 >> results/s19/rtl_big2.jsonl 2>>results/s19/rtl11.err
done
echo ALLDONE >> results/s19/rtl11.err
