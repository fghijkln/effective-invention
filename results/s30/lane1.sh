source ~/env.sh; cd /workspace/work/omega
export PYTHONPATH=.:tests PYTHONUNBUFFERED=1 OMEGA_SPLIT=400 OMEGA_JOBS=1 OMEGA_BUILD=/tmp/b_L1
unset OMEGA_RTO OMEGA_RGRAD OMEGA_RSV OMEGA_LM OMEGA_ADM OMEGA_LM_AHI OMEGA_PASSON OMEGA_ILR
ulimit -v 4500000
python3 results/s30/validate.py big >> results/s30/val_big.out 2>&1; echo "big $?" >> results/s30/lane1.status
python3 tests/test_s30.py > results/s30/s30_full.log 2>&1; echo "s30 $? $(tail -n 1 results/s30/s30_full.log)" >> results/s30/lane1.status
touch results/s30/lane1.done
