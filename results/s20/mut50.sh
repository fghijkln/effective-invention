source ~/env.sh; cd /workspace/work/omega
export PYTHONPATH=.:tests PYTHONUNBUFFERED=1 OMEGA_SPLIT=800 OMEGA_JOBS=1
unset OMEGA_RTO OMEGA_RGRAD OMEGA_RSV; ulimit -v 4500000
python3 tests/mutants.py 50 > results/s20/mut50.txt 2>&1; echo "rc $?" >> results/s20/mut50.txt
