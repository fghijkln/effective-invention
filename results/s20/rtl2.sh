source ~/env.sh; cd /workspace/work/omega; ulimit -v 4500000; export OMEGA_JOBS=1 PYTHONPATH=.:tests
OMEGA_RSV=1 python3 results/s20/rtl_ts9.py 1 30 >> results/s20/rtl_ts9.jsonl 2>>results/s20/rtl2.err
OMEGA_RSV=1 python3 results/s20/rtl_big.py 1 13 0 3 4 >> results/s20/rtl1.jsonl 2>>results/s20/rtl2.err
echo DONE >> results/s20/rtl_ts9.jsonl
