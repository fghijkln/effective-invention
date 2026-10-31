[ -f ~/env.sh ] || bash /workspace/work/setup_tc_noyosys.sh > /workspace/work/omega/results/s22/tc.log 2>&1; source ~/env.sh
cd /workspace/work/omega
export PYTHONPATH=.:tests PYTHONUNBUFFERED=1 OMEGA_SPLIT=400 OMEGA_JOBS=1
unset OMEGA_RTO OMEGA_RGRAD OMEGA_RSV OMEGA_LM OMEGA_ADM OMEGA_LM_AHI OMEGA_PASSON
ulimit -v 4500000
python3 tests/mutants.py $(cat results/s22/mut_rest.bits) >> results/s22/mut_rest.txt 2>&1
touch results/s22/mut_rest.done
