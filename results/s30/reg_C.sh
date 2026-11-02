# lane C: lane B tail in reverse order (shares reg_B.status), starts after lane A
while [ ! -f ~/env.sh ]; do sleep 15; done; source ~/env.sh
cd /workspace/work/omega
export PYTHONPATH=.:tests PYTHONUNBUFFERED=1 OMEGA_SPLIT=400 OMEGA_JOBS=1 OMEGA_BUILD=/tmp/b_C30
unset OMEGA_RTO OMEGA_RGRAD OMEGA_RSV OMEGA_LM OMEGA_ADM OMEGA_LM_AHI OMEGA_PASSON OMEGA_ILR
ulimit -v 4500000
L=results/s30/reg_B.status; [ -f $L ] || : > $L
step(){ grep -q "^$1 " $L && return 1; return 0; }
while [ ! -f results/s30/reg_A.done ]; do sleep 20; done
if step s27; then python3 tests/test_s27.py > results/s30/s27.log 2>&1; echo "s27 $? $(tail -n 1 results/s30/s27.log)" >> $L; fi
if step s26mut; then python3 tests/test_s26.py --mutants > results/s30/s26_mutants.log 2>&1; echo "s26mut $? $(tail -n 1 results/s30/s26_mutants.log)" >> $L; fi
if step s26; then python3 tests/test_s26.py > results/s30/s26.log 2>&1; echo "s26 $? $(tail -n 1 results/s30/s26.log)" >> $L; fi
if step s25mut; then python3 tests/test_s25.py --mutants > results/s30/s25_mutants.log 2>&1; echo "s25mut $? $(tail -n 1 results/s30/s25_mutants.log)" >> $L; fi
if step s25; then python3 tests/test_s25.py > results/s30/s25.log 2>&1; echo "s25 $? $(tail -n 1 results/s30/s25.log)" >> $L; fi
if step ealmut; then python3 tests/test_eal.py --mutants > results/s30/eal_mutants.log 2>&1; echo "ealmut $? $(tail -n 1 results/s30/eal_mutants.log)" >> $L; fi
if step eal; then python3 tests/test_eal.py --fuzz 200 --rtl-fuzz 30 > results/s30/eal.log 2>&1; echo "eal $? $(tail -n 1 results/s30/eal.log)" >> $L; fi
touch results/s30/reg_C.done
