source ~/env.sh
cd /workspace/work/omega
export PYTHONPATH=.:tests PYTHONUNBUFFERED=1 OMEGA_SPLIT=400 OMEGA_JOBS=1
unset OMEGA_RTO OMEGA_RGRAD OMEGA_RSV OMEGA_LM
ulimit -v 4500000
python3 tests/mutants.py > results/mutants.txt 2>&1; echo "rc $?" >> results/mutants.txt
tail -n 2 results/mutants.txt > results/mutants.log
touch results/s21/mut.done
