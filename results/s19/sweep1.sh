cd /workspace/work/omega
ulimit -v 1500000
O=results/s19/sweep1.jsonl
run(){ env OMEGA_RTO=$1 OMEGA_RBO=$2 OMEGA_RJIT=$3 OMEGA_RRST=$4 python3 results/s19/sw19.py "rto$1-bo$2-j$3-r$4" >> $O; }
run 32 0 0 0; run 8 0 0 0
for r in 0 1; do for b in 1 2 3; do run 8 $b 0 $r; done; done
for b in 2 3; do run 8 $b 3 0; done
run 8 0 3 0
echo DONE >> $O
