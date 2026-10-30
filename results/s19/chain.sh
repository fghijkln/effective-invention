source ~/env.sh
cd /workspace/work/omega
while ! grep -q ALLDONE results/s19/rtl11.err 2>/dev/null; do sleep 20; done
export PYTHONPATH=.:tests PYTHONUNBUFFERED=1 OMEGA_SPLIT=800 OMEGA_JOBS=1
unset OMEGA_RTO OMEGA_RGRAD
ulimit -v 4500000
P=qsort:40,list:120,sum:1000,sort:20,higher:100,fib:20,treesum:9,treesum_direct:14
python3 bench/sweep14.py $P 4x4 2 8 results/s19/id_4x4.jsonl > results/s19/id.log 2>&1
python3 bench/sweep14.py $P 8x8 2 8 results/s19/id_8x8.jsonl >> results/s19/id.log 2>&1
python3 results/s19/idcmp.py > results/s19/idcmp.txt 2>&1
echo IDDONE >> results/s19/id.log
