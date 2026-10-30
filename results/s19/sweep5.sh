cd /workspace/work/omega
ulimit -v 1500000
O=results/s19/sweep5.jsonl
OMEGA_RTO=8 OMEGA_RGRAD=3 nice -n 15 python3 results/s19/sw19b.py rto8-g3 21 40 | tail -1 >> $O
OMEGA_RTO=8 OMEGA_RGRAD=0 nice -n 15 python3 results/s19/sw19b.py rto8-g0 21 40 | tail -1 >> $O
OMEGA_RTO=32 OMEGA_RGRAD=0 nice -n 15 python3 results/s19/sw19b.py rto32-g0 21 40 | tail -1 >> $O
echo DONE >> $O
