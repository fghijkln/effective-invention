cd /workspace/work/omega; export PYTHONPATH=.:tests
r(){ K=$1; shift; echo "== K=$K $*"; env "$@" python3 results/s20/cex.py $K 1-20; }
r 600 X=0
r 800 X=0
r 400 X=0
r 120 OMEGA_ADM=24
r 1024 OMEGA_ADM=24
for f in 1.3 2.0; do OMEGA_ADM=0 python3 results/s22/near.py $f 10; OMEGA_ADM=24 python3 results/s22/near.py $f 10; OMEGA_ADM=8 OMEGA_LM_AHI=512 python3 results/s22/near.py $f 10; done
