# Step 29 regression at defaults (resumable: finished steps are recorded in results/s29/reg.status)
[ -f ~/env.sh ] || bash /workspace/work/setup_tc_noyosys.sh > /dev/null 2>&1; source ~/env.sh
cd /workspace/work/omega
export PYTHONPATH=.:tests PYTHONUNBUFFERED=1 OMEGA_SPLIT=400 OMEGA_JOBS=1 OMEGA_BUILD=/tmp/b_A29
unset OMEGA_RTO OMEGA_RGRAD OMEGA_RSV OMEGA_LM OMEGA_ADM OMEGA_LM_AHI OMEGA_PASSON OMEGA_ILR
ulimit -v 4500000

P=qsort:40,list:120,sum:1000,sort:20,higher:100,fib:20,treesum:9,treesum_direct:14
L=results/s29/reg_A.status; [ -f $L ] || : > $L
step(){ grep -q "^$1 " $L && return 1; return 0; }
if step id4; then python3 bench/sweep14.py $P 4x4 2 8 results/s29/id_4x4.jsonl > results/s29/id4.log 2>&1; echo "id4 $? $(wc -l < results/s29/id_4x4.jsonl)" >> $L; fi
if step id8; then python3 bench/sweep14.py $P 8x8 2 8 results/s29/id_8x8.jsonl > results/s29/id8.log 2>&1; echo "id8 $? $(wc -l < results/s29/id_8x8.jsonl)" >> $L; fi
if step id; then python3 results/s29/idcmp.py > results/s29/idcmp.txt 2>&1; echo "id $(head -n 1 results/s29/idcmp.txt)" >> $L; fi
if step units; then python3 tests/test_units.py --rtl > results/units_rtl.log 2>&1; echo "units $? $(tail -n 1 results/units_rtl.log)" >> $L; fi
if step programs; then python3 tests/test_programs.py --fuzz 150 > results/programs.log 2>&1; echo "programs $? $(tail -n 1 results/programs.log)" >> $L; fi
if step s14; then python3 tests/test_s14.py > results/s14_cross.log 2>&1; echo "s14 $? $(tail -n 1 results/s14_cross.log)" >> $L; fi
if step fuzz; then python3 tests/fuzz_rtl.py 0 600 --out /tmp/fz.jsonl > /tmp/fz.log 2>&1; tail -n 3 /tmp/fz.log > results/fuzz_rtl.log; echo "fuzz $(tail -n 1 results/fuzz_rtl.log)" >> $L; rm -f /tmp/fz.jsonl; fi
if step bigfuzz; then python3 tests/fuzz_rtl.py 0 200 --big --out /tmp/fzb.jsonl > /tmp/fzb.log 2>&1; tail -n 3 /tmp/fzb.log > results/fuzz_rtl_big.log; echo "bigfuzz $(tail -n 1 results/fuzz_rtl_big.log)" >> $L; rm -f /tmp/fzb.jsonl; fi
if step security; then python3 tests/test_security.py --fuzz 300 > results/security.log 2>&1; echo "security $? $(tail -n 1 results/security.log)" >> $L; fi
if step mempress; then python3 tests/test_mempress.py > results/mempress.log 2>&1; echo "mempress $? $(tail -n 1 results/mempress.log)" >> $L; fi
echo ALLDONE >> $L
touch results/s29/reg_A.done
