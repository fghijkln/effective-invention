cd /workspace/work/omega; ulimit -v 1500000
python3 results/s20/minkeep.py treesum 9 > results/s20/minkeep.txt 2>&1
RHI=64 RLO=32 python3 results/s20/cex.py 200 1-10 >> results/s20/cex.jsonl
RHI=64 RLO=32 python3 results/s20/cex.py 130 1-10 >> results/s20/cex.jsonl
echo DONE2 >> results/s20/cex.jsonl
