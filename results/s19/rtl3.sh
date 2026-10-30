source ~/env.sh
cd /workspace/work/omega
ulimit -v 4500000
export PYTHONPATH=.:tests OMEGA_JOBS=1 OMEGA_SPLIT=800
O=results/s19/rtl_ts9.jsonl
for cfg in "32 0" "8 0" "8 7"; do set -- $cfg
  OMEGA_RTO=$1 OMEGA_RGRAD=$2 OMEGA_XARGS="rgrad=$2" python3 results/s19/rtl_ts9.py 11 30 >> $O 2>>results/s19/rtl3.err
done
echo DONE2 >> $O
G=results/s19/rto_global_g.jsonl
OMEGA_RTO=8 OMEGA_RGRAD=7 python3 bench/rto18_rtl.py 3 >> $G 2>>results/s19/rtl3.err
echo DONE >> $G
