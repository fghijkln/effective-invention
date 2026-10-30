cd /workspace/work/omega
ulimit -v 1500000
O=results/s19/sweep2.txt
for w in 512 384 256; do for k in 2 4 8; do OMEGA_RTO=8 OMEGA_AGE=$k OMEGA_AGEW=$w python3 results/s19/quick.py 1 10 >> $O; done; done
echo DONE >> $O
