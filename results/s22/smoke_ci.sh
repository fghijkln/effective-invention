source ~/env.sh; cd /workspace/work/omega
export PYTHONPATH=.:tests PYTHONUNBUFFERED=1 OMEGA_SPLIT=400 OMEGA_JOBS=1
unset OMEGA_LM OMEGA_ADM
python3 results/s22/near_smoke.py > results/s22/near_smoke.log 2>&1
bash tests/ci_quick.sh > results/s22/ci_quick.log 2>&1; echo "rc $?" >> results/s22/ci_quick.log
touch results/s22/smoke_ci.done
