# resumable: runs the mutants of 37..54 not yet in results/s24/mut_c.txt (after a sandbox restart)
while [ ! -f ~/env.sh ]; do sleep 10; done; sleep 5
source ~/env.sh; cd /workspace/work/omega
export PYTHONPATH=.:tests PYTHONUNBUFFERED=1 OMEGA_SPLIT=400 OMEGA_JOBS=1
unset OMEGA_RTO OMEGA_RGRAD OMEGA_RSV OMEGA_LM OMEGA_ADM OMEGA_LM_AHI OMEGA_PASSON OMEGA_ILR
ulimit -v 4500000
todo=""; for i in $(seq 37 54); do grep -q "^mutant $(printf '%2d' $i) " results/s24/mut_c.txt 2>/dev/null || todo="$todo $i"; done
[ -n "$todo" ] && python3 tests/mutants.py $todo >> results/s24/mut_c.txt 2>&1
c=$(grep -c "CAUGHT" results/s24/mut_c.txt); echo "mutCres $c/18 caught (37-54)" >> results/s24/reg.status
