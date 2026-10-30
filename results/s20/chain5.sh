cd /workspace/work/omega; ulimit -v 1500000
r(){ tag=$1; shift; env "$@" python3 results/s20/perf.py $tag 1-20 t6,l20,f6,t9 >> results/s20/sw4.jsonl; }
r rg2off OMEGA_RG2=0
r rsv1rg2off OMEGA_RSV=1 OMEGA_RG2=0
r rsv0rgm0 OMEGA_RSV=0 OMEGA_RGM=0
echo DONE >> results/s20/sw4.jsonl
for K in 130 200 300; do
  python3 results/s20/cex.py $K 1-20 >> results/s20/cex.jsonl
  OMEGA_RTO=32 OMEGA_RGRAD=0 python3 results/s20/cex.py $K 1-20 >> results/s20/cex.jsonl
done
echo DONE >> results/s20/cex.jsonl
