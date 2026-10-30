source ~/env.sh; cd /workspace/work/omega; ulimit -v 4500000; export OMEGA_JOBS=1 PYTHONPATH=.:tests
for R in 4 1 0; do OMEGA_RSV=$R python3 results/s20/rtl_big.py 1 13 1 2 >> results/s20/rtl1.jsonl 2>>results/s20/rtl1.err; done
echo DONE >> results/s20/rtl1.jsonl
