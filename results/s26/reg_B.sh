# Step 26 regression at defaults (resumable: finished steps are recorded in results/s26/reg.status)
[ -f ~/env.sh ] || bash /workspace/work/setup_tc_noyosys.sh > /dev/null 2>&1; source ~/env.sh
cd /workspace/work/omega
export PYTHONPATH=.:tests PYTHONUNBUFFERED=1 OMEGA_SPLIT=400 OMEGA_JOBS=1 OMEGA_BUILD=/tmp/b_B
unset OMEGA_RTO OMEGA_RGRAD OMEGA_RSV OMEGA_LM OMEGA_ADM OMEGA_LM_AHI OMEGA_PASSON OMEGA_ILR
ulimit -v 4500000

P=qsort:40,list:120,sum:1000,sort:20,higher:100,fib:20,treesum:9,treesum_direct:14
L=results/s26/reg_B.status; [ -f $L ] || : > $L
step(){ grep -q "^$1 " $L && return 1; return 0; }
if step mutA; then python3 tests/mutants.py 16 17 18 > results/s26/mut_a2.txt 2>&1; rc=$?; echo "mutA $rc 0-15: $(grep -c CAUGHT results/s26/mut_a_0_15.txt) caught (mut_a_0_15.txt) + 16-18: $(tail -n 1 results/s26/mut_a2.txt)" >> $L; fi
if step mutB; then python3 tests/mutants.py $(seq 19 36) > results/s26/mut_b.txt 2>&1; echo "mutB $? $(tail -n 1 results/s26/mut_b.txt)" >> $L; fi
if step mutC; then python3 tests/mutants.py $(seq 37 54) > results/s26/mut_c.txt 2>&1; echo "mutC $? $(tail -n 1 results/s26/mut_c.txt)" >> $L; fi
if step eal; then python3 tests/test_eal.py --fuzz 200 --rtl-fuzz 30 > results/s26/eal_final.log 2>&1; echo "eal $? $(tail -n 1 results/s26/eal_final.log)" >> $L; fi
if step ealmut; then python3 tests/test_eal.py --mutants > results/s26/eal_mutants.log 2>&1; echo "ealmut $? $(tail -n 1 results/s26/eal_mutants.log)" >> $L; fi
if step s25; then python3 tests/test_s25.py > results/s26/s25_full.log 2>&1; echo "s25 $? $(tail -n 1 results/s26/s25_full.log)" >> $L; fi
if step s25mut; then python3 tests/test_s25.py --mutants > results/s26/s25_mutants.log 2>&1; echo "s25mut $? $(tail -n 1 results/s26/s25_mutants.log)" >> $L; fi
if step s26; then python3 tests/test_s26.py --json results/s26/s26_final.json > results/s26/s26_final.log 2>&1; echo "s26 $? $(tail -n 1 results/s26/s26_final.log)" >> $L; fi
if step s27; then python3 tests/test_s27.py --json results/s27/s27_final.json > results/s27/s27_final.log 2>&1; echo "s27 $? $(tail -n 1 results/s27/s27_final.log)" >> $L; fi
echo ALLDONE >> $L
touch results/s26/reg_B.done
