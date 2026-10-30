cd /workspace/work/omega
ulimit -v 1500000
O=results/s19/sweep4.jsonl
for g in 3 2 4; do OMEGA_RTO=8 OMEGA_RGRAD=$g OMEGA_RGM=1 nice -n 15 python3 results/s19/sw19.py rto8-g$g-rgm1 >> $O; done
echo DONE >> $O
