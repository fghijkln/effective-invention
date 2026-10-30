cd /workspace/work/omega
ulimit -v 1500000
OMEGA_RTO=8 OMEGA_RGRAD=3 OMEGA_RSV=4 nice -n 15 python3 results/s19/sw19.py rto8-g3-rsv4 >> results/s19/sweep6.jsonl
OMEGA_RTO=8 OMEGA_RGRAD=3 OMEGA_RSV=4 nice -n 15 python3 results/s19/sw19b.py rto8-g3-rsv4 21 40 | tail -1 >> results/s19/sweep6.jsonl
echo DONE >> results/s19/sweep6.jsonl
