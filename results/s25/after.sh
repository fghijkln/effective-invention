# Step 25: after reg.sh: final Ω-L tests (step 24 suite, unchanged) and Ω-L mutants
cd /workspace/work/omega
while [ ! -f results/s25/reg.done ]; do sleep 30; done
source ~/env.sh; export PYTHONPATH=.:tests PYTHONUNBUFFERED=1 OMEGA_SPLIT=400 OMEGA_JOBS=1
python3 tests/test_eal.py --fuzz 200 --rtl-fuzz 30 > results/s25/eal_final.log 2>&1; echo "eal $? $(tail -n 1 results/s25/eal_final.log)" >> results/s25/reg.status
python3 tests/test_eal.py --mutants > results/s25/eal_mutants.log 2>&1; echo "ealmut $? $(tail -n 1 results/s25/eal_mutants.log)" >> results/s25/reg.status
touch results/s25/after.done
