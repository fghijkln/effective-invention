cd /workspace/work/omega; export PYTHONPATH=.:tests
r(){ K=$1; shift; echo "== K=$K $*"; env "$@" python3 results/s20/cex.py $K 1-20; }
r 300 RHI=64 RLO=32 OMEGA_RSV=16
r 300 OMEGA_ADM=8 OMEGA_LM_AHI=512
r 500 X=0
r 500 RHI=64 RLO=32 OMEGA_RSV=16
r 500 OMEGA_ADM=8 OMEGA_LM_AHI=512
r 200 OMEGA_ADM=8 OMEGA_LM_AHI=512
