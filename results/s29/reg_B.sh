# Step 29 regression lane B (resumable)
[ -f ~/env.sh ] || bash /workspace/work/setup_tc_noyosys.sh > /dev/null 2>&1; source ~/env.sh
cd /workspace/work/omega
export PYTHONPATH=.:tests PYTHONUNBUFFERED=1 OMEGA_SPLIT=400 OMEGA_JOBS=1 OMEGA_BUILD=/tmp/b_B29
unset OMEGA_RTO OMEGA_RGRAD OMEGA_RSV OMEGA_LM OMEGA_ADM OMEGA_LM_AHI OMEGA_PASSON OMEGA_ILR
ulimit -v 4500000
L=results/s29/reg_B.status; [ -f $L ] || : > $L
step(){ grep -q "^$1 " $L && return 1; return 0; }
if step s29; then python3 tests/test_s29.py --json results/s29/s29.json > results/s29/s29_full.log 2>&1; echo "s29 $? $(tail -n 1 results/s29/s29_full.log)" >> $L; fi
if step s29mut; then python3 tests/test_s29.py --mutants > results/s29/s29_mut.log 2>&1; echo "s29mut $? $(tail -n 1 results/s29/s29_mut.log)" >> $L; fi
if step s28; then python3 tests/test_s28.py --json results/s29/s28.json > results/s29/s28_full.log 2>&1; echo "s28 $? $(tail -n 1 results/s29/s28_full.log)" >> $L; fi
if step s28mut; then python3 tests/test_s28.py --mutants > results/s29/s28_mut.log 2>&1; echo "s28mut $? $(tail -n 1 results/s29/s28_mut.log)" >> $L; fi
for k in $(seq 0 54); do
  if step mut$k; then python3 tests/mutants.py $k > results/s29/mut_$k.txt 2>&1; echo "mut$k $? $(tail -n 1 results/s29/mut_$k.txt)" >> $L; fi
done
if step eal; then python3 tests/test_eal.py --fuzz 200 --rtl-fuzz 30 > results/s29/eal.log 2>&1; echo "eal $? $(tail -n 1 results/s29/eal.log)" >> $L; fi
if step ealmut; then python3 tests/test_eal.py --mutants > results/s29/eal_mutants.log 2>&1; echo "ealmut $? $(tail -n 1 results/s29/eal_mutants.log)" >> $L; fi
if step s25; then python3 tests/test_s25.py > results/s29/s25.log 2>&1; echo "s25 $? $(tail -n 1 results/s29/s25.log)" >> $L; fi
if step s25mut; then python3 tests/test_s25.py --mutants > results/s29/s25_mutants.log 2>&1; echo "s25mut $? $(tail -n 1 results/s29/s25_mutants.log)" >> $L; fi
if step s26; then python3 tests/test_s26.py > results/s29/s26.log 2>&1; echo "s26 $? $(tail -n 1 results/s29/s26.log)" >> $L; fi
if step s26mut; then python3 tests/test_s26.py --mutants > results/s29/s26_mutants.log 2>&1; echo "s26mut $? $(tail -n 1 results/s29/s26_mutants.log)" >> $L; fi
if step s27; then python3 tests/test_s27.py > results/s29/s27.log 2>&1; echo "s27 $? $(tail -n 1 results/s29/s27.log)" >> $L; fi
echo ALLDONE >> $L
touch results/s29/reg_B.done
