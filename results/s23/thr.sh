source ~/env.sh; cd /workspace/work/omega; export PYTHONPATH=.:tests OMEGA_SPLIT=400 OMEGA_JOBS=1 PYTHONUNBUFFERED=1
python3 results/s23/thr.py 0:0 2:0x20000000000000 2:0x40000000000000 1:0x20000000000000 > results/s23/thr.log 2>&1
echo DONE >> results/s23/thr.log
