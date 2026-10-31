cd /workspace/work/omega; export PYTHONPATH=.:tests
for K in 200 150 120 300; do for a in 8 0; do echo "== K=$K ADM=$a"; OMEGA_ADM=$a python3 results/s20/cex.py $K 1-20; done; done
