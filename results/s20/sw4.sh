cd /workspace/work/omega; ulimit -v 1500000
while ! grep -q DONE results/s20/cex.jsonl 2>/dev/null; do sleep 10; done
r(){ tag=$1; shift; env "$@" python3 results/s20/perf.py $tag 1-20 t6,l20,f6,t9 >> results/s20/sw4.jsonl; }
r rg2off OMEGA_RG2=0
r rsv0rgm0 OMEGA_RSV=0 OMEGA_RGM=0
r rsv0rg2off OMEGA_RSV=0 OMEGA_RG2=0
r rsv0rgm0rg2off OMEGA_RSV=0 OMEGA_RGM=0 OMEGA_RG2=0
echo DONE >> results/s20/sw4.jsonl
