cd /workspace/work/omega
ulimit -v 1500000
O=results/s19/sweep3.jsonl
OMEGA_RTO=8 OMEGA_RGRAD=7 OMEGA_RGM=1 python3 results/s19/sw19.py rto8-g7-rgm1 >> $O
OMEGA_RTO=8 OMEGA_RGRAD=7 OMEGA_RGM=2 python3 results/s19/sw19.py rto8-g7-rgm2 >> $O
OMEGA_RTO=8 OMEGA_RGRAD=7 OMEGA_RGM=0 python3 results/s19/sw19.py rto8-g7-esc-only >> $O
OMEGA_RTO=32 OMEGA_RGRAD=7 OMEGA_RGM=1 python3 results/s19/sw19.py rto32-g7-rgm1 >> $O
echo DONE >> $O
