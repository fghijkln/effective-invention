cd /workspace/work/omega; ulimit -v 1500000
OMEGA_RSV=0 OMEGA_RGM=0 OMEGA_RG2=0 python3 results/s20/perf.py rsv0rgm0rg2off 1-20 t6,l20,f6,t9 >> results/s20/sw4.jsonl
echo DONE8 >> results/s20/sw4.jsonl
