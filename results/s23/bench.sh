[ -f ~/env.sh ] || bash /workspace/work/setup_tc_noyosys.sh > /dev/null 2>&1; source ~/env.sh
cd /workspace/work/omega
export PYTHONPATH=.:tests PYTHONUNBUFFERED=1 OMEGA_SPLIT=400 OMEGA_JOBS=1
unset OMEGA_RTO OMEGA_RGRAD OMEGA_RSV OMEGA_LM OMEGA_ADM OMEGA_LM_AHI OMEGA_PASSON
ulimit -v 4500000
L=results/s23/bench.status; [ -f $L ] || : > $L
step(){ grep -q "^$1 " $L && return 1; return 0; }
P=qsort:40,list:120,sum:1000,sort:20,higher:100,fib:20,treesum:9,treesum_direct:14
for i in 1 2; do
  if step b4_$i; then OMEGA_ILR=$i python3 bench/sweep14.py $P 1x1,2x2,4x4 2 8 results/s23/b4_ilr$i.jsonl > results/s23/b4_$i.log 2>&1; echo "b4_$i $? $(wc -l < results/s23/b4_ilr$i.jsonl)" >> $L; fi
done
for i in 1 2; do
  if step b8_$i; then OMEGA_ILR=$i python3 bench/sweep14.py $P 8x8 2 8 results/s23/b8_ilr$i.jsonl > results/s23/b8_$i.log 2>&1; echo "b8_$i $? $(wc -l < results/s23/b8_ilr$i.jsonl)" >> $L; fi
done
echo ALLDONE >> $L
