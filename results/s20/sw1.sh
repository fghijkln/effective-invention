cd /workspace/work/omega; ulimit -v 1500000
r(){ tag=$1; shift; env "$@" python3 results/s20/perf.py $tag 1-20 t6,l20,f6,t9 >> results/s20/sw1.jsonl; }
r r32g0 OMEGA_RTO=32 OMEGA_RGRAD=0
r r8g0 OMEGA_RTO=8 OMEGA_RGRAD=0
r def X=1
for v in 0 1 2 3; do r rsv$v OMEGA_RSV=$v; done
r rgm0 OMEGA_RGM=0
r rgm2 OMEGA_RGM=2
echo DONE >> results/s20/sw1.jsonl
