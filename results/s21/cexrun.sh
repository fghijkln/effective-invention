# step 22: treesum(9) 3x3 counterexample (corner 200 free, others 8) under admission knobs, 20 seeds each
cd /workspace/work/omega; export PYTHONPATH=.:tests
run(){ echo "== $*"; env "$@" python3 results/s20/cex.py 200 1-20; }
run X=0
run OMEGA_ADM=1
run OMEGA_ADM=1 OMEGA_ADM_W=16
run OMEGA_ADM=2 OMEGA_LM_T=1000000
run OMEGA_ADM=6 OMEGA_LM_T=1000000
run OMEGA_ADM=7 OMEGA_LM_T=1000000
run OMEGA_RSV=16
run OMEGA_RSV=64
run OMEGA_RSV=130
