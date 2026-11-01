# resumable: runs the mutants of 19..36 not yet in results/s25/mut_b.txt (after a sandbox restart)
while [ ! -f ~/env.sh ]; do sleep 10; done; sleep 5
source ~/env.sh; cd /workspace/work/omega; export OMEGA_BUILD=/tmp/omega_build_mb
export PYTHONPATH=.:tests PYTHONUNBUFFERED=1 OMEGA_SPLIT=400 OMEGA_JOBS=1
unset OMEGA_RTO OMEGA_RGRAD OMEGA_RSV OMEGA_LM OMEGA_ADM OMEGA_LM_AHI OMEGA_PASSON OMEGA_ILR
ulimit -v 4500000
todo=""; for i in $(seq 19 36); do grep -q "^mutant $(printf '%2d' $i) " results/s25/mut_b.txt 2>/dev/null || todo="$todo $i"; done
[ -n "$todo" ] && python3 tests/mutants.py $todo >> results/s25/mut_b.txt 2>&1
c=$(grep -c "CAUGHT" results/s25/mut_b.txt); echo "mutBres $c/18 caught (19-36)" >> results/s25/reg.status
