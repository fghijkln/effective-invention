# Step 29 regression lane B (resumable)
[ -f ~/env.sh ] || bash /workspace/work/setup_tc_noyosys.sh > /dev/null 2>&1; source ~/env.sh
cd /workspace/work/omega
export PYTHONPATH=.:tests PYTHONUNBUFFERED=1 OMEGA_SPLIT=400 OMEGA_JOBS=1 OMEGA_BUILD=/tmp/b_B29
unset OMEGA_RTO OMEGA_RGRAD OMEGA_RSV OMEGA_LM OMEGA_ADM OMEGA_LM_AHI OMEGA_PASSON OMEGA_ILR
ulimit -v 4500000
L=results/s29/reg_B.status; [ -f $L ] || : > $L
step(){ grep -q "^$1 " $L && return 1; return 0; }
if step s29; then python3 tests/test_s29.py --json results/s29/s29.json > results/s29/s29_full.log 2>&1; echo "s29 $? $(tail -n 1 results/s29/s29_full.log)" >> $L; fi
for k in $(seq 47 54); do
  if step mut$k; then python3 tests/mutants.py $k > results/s29/mut_$k.txt 2>&1; echo "mut$k $? $(tail -n 1 results/s29/mut_$k.txt)" >> $L; fi
done
touch results/s29/reg_B2.done
