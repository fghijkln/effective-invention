cd /workspace/work/omega; ulimit -v 1500000
while ! grep -q DONE results/s20/cex.jsonl 2>/dev/null; do sleep 10; done
env python3 results/s20/perf.py def 1-20 f3,q4,s10 >> results/s20/sw6.jsonl
OMEGA_RSV=1 python3 results/s20/perf.py rsv1 1-20 f3,q4,s10 >> results/s20/sw6.jsonl
OMEGA_RSV=1 python3 results/s20/perf.py rsv1 21-40 l20,q6,f6,t7 >> results/s20/sw6.jsonl
OMEGA_RSV=0 python3 results/s20/perf.py rsv0 21-40 l20,q6,f6,t7 >> results/s20/sw6.jsonl
echo DONE >> results/s20/sw6.jsonl
