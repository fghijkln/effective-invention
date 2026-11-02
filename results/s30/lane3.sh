source ~/env.sh; cd /workspace/work/omega
export PYTHONPATH=.:tests PYTHONUNBUFFERED=1 OMEGA_SPLIT=400 OMEGA_JOBS=1 OMEGA_BUILD=/tmp/b_L1
unset OMEGA_RTO OMEGA_RGRAD OMEGA_RSV OMEGA_LM OMEGA_ADM OMEGA_LM_AHI OMEGA_PASSON OMEGA_ILR
ulimit -v 4500000
python3 tests/test_s29.py --json results/s30/s29.json > results/s30/s29_full.log 2>&1; echo "s29 $? $(tail -n 1 results/s30/s29_full.log)" >> results/s30/lane3.status
touch results/s30/lane3.done
