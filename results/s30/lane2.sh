source ~/env.sh; cd /workspace/work/omega
export PYTHONPATH=.:tests PYTHONUNBUFFERED=1 OMEGA_SPLIT=400 OMEGA_JOBS=1 OMEGA_BUILD=/tmp/b_A30
unset OMEGA_RTO OMEGA_RGRAD OMEGA_RSV OMEGA_LM OMEGA_ADM OMEGA_LM_AHI OMEGA_PASSON OMEGA_ILR
ulimit -v 4500000
P=qsort:40,list:120,sum:1000,sort:20,higher:100,fib:20,treesum:9,treesum_direct:14
L=results/s30/reg_A.status
step(){ grep -q "^$1 " $L && return 1; return 0; }
if step id8; then python3 bench/sweep14.py $P 8x8 2 8 results/s30/id_8x8.jsonl > results/s30/id8.log 2>&1; echo "id8 $? $(wc -l < results/s30/id_8x8.jsonl)" >> $L; fi
if step id; then python3 results/s30/idcmp.py > results/s30/idcmp.txt 2>&1; echo "id $(head -n 1 results/s30/idcmp.txt)" >> $L; fi
if step units; then python3 tests/test_units.py --rtl > results/units_rtl.log 2>&1; echo "units $? $(tail -n 1 results/units_rtl.log)" >> $L; fi
if step programs; then python3 tests/test_programs.py --fuzz 150 > results/programs.log 2>&1; echo "programs $? $(tail -n 1 results/programs.log)" >> $L; fi
if step s14; then python3 tests/test_s14.py > results/s14_cross.log 2>&1; echo "s14 $? $(tail -n 1 results/s14_cross.log)" >> $L; fi
touch results/s30/lane2.done
