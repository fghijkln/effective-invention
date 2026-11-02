source ~/env.sh; cd /workspace/work/omega
export PYTHONPATH=.:tests PYTHONUNBUFFERED=1 OMEGA_SPLIT=400 OMEGA_JOBS=1 OMEGA_BUILD=/tmp/b_L1
unset OMEGA_RTO OMEGA_RGRAD OMEGA_RSV OMEGA_LM OMEGA_ADM OMEGA_LM_AHI OMEGA_PASSON OMEGA_ILR
ulimit -v 4500000
python3 tests/fuzz_rtl.py 0 600 --out /tmp/fz.jsonl > /tmp/fz.log 2>&1; tail -n 3 /tmp/fz.log > results/fuzz_rtl.log; echo "fuzz $(tail -n 1 results/fuzz_rtl.log)" >> results/s30/lane3.status
python3 tests/test_mempress.py > results/mempress.log 2>&1; echo "mempress $? $(tail -n 1 results/mempress.log)" >> results/s30/lane3.status
touch results/s30/lane4.done
