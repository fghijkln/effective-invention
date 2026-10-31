[ -f ~/env.sh ] || bash /workspace/work/setup_tc_noyosys.sh > /dev/null 2>&1; source ~/env.sh
cd /workspace/work/omega
export PYTHONPATH=.:tests PYTHONUNBUFFERED=1 OMEGA_SPLIT=400 OMEGA_JOBS=1
unset OMEGA_RTO OMEGA_RGRAD OMEGA_RSV OMEGA_LM OMEGA_ADM OMEGA_LM_AHI OMEGA_PASSON OMEGA_ILR
ulimit -v 4500000
L=results/s23/reg.status; [ -f $L ] || : > $L
step(){ grep -q "^$1 " $L && return 1; return 0; }
P=qsort:40,list:120,sum:1000,sort:20,higher:100,fib:20,treesum:9,treesum_direct:14
if step id4; then python3 bench/sweep14.py $P 4x4 2 8 results/s23/id_4x4.jsonl > results/s23/id4.log 2>&1; echo "id4 $? $(wc -l < results/s23/id_4x4.jsonl)" >> $L; fi
if step id8; then python3 bench/sweep14.py $P 8x8 2 8 results/s23/id_8x8.jsonl > results/s23/id8.log 2>&1; echo "id8 $? $(wc -l < results/s23/id_8x8.jsonl)" >> $L; fi
if step id; then python3 results/s23/idcmp.py > results/s23/idcmp.txt 2>&1; echo "id $(head -n 1 results/s23/idcmp.txt)" >> $L; fi
if step units; then python3 tests/test_units.py --rtl > results/units_rtl.log 2>&1; echo "units $? $(tail -n 1 results/units_rtl.log)" >> $L; fi
if step programs; then python3 tests/test_programs.py --fuzz 150 > results/programs.log 2>&1; echo "programs $? $(tail -n 1 results/programs.log)" >> $L; fi
if step s14; then python3 tests/test_s14.py > results/s14_cross.log 2>&1; echo "s14 $? $(tail -n 1 results/s14_cross.log)" >> $L; fi
if step fuzz; then python3 tests/fuzz_rtl.py 0 600 --out /tmp/fz.jsonl > /tmp/fz.log 2>&1; tail -n 3 /tmp/fz.log > results/fuzz_rtl.log; echo "fuzz $(tail -n 1 results/fuzz_rtl.log)" >> $L; rm -f /tmp/fz.jsonl; fi
if step bigfuzz; then python3 tests/fuzz_rtl.py 0 200 --big --out /tmp/fzb.jsonl > /tmp/fzb.log 2>&1; tail -n 3 /tmp/fzb.log > results/fuzz_rtl_big.log; echo "bigfuzz $(tail -n 1 results/fuzz_rtl_big.log)" >> $L; rm -f /tmp/fzb.jsonl; fi
if step security; then python3 tests/test_security.py --fuzz 300 > results/security.log 2>&1; echo "security $? $(tail -n 1 results/security.log)" >> $L; fi
if step mempress; then python3 tests/test_mempress.py > results/mempress.log 2>&1; echo "mempress $? $(tail -n 1 results/mempress.log)" >> $L; fi
# knob correctness (+ilr=1, +ilr=2)
if step k2units; then OMEGA_ILR=2 python3 tests/test_units.py --rtl > results/s23/k2_units.log 2>&1; echo "k2units $? $(tail -n 1 results/s23/k2_units.log)" >> $L; fi
if step k2programs; then OMEGA_ILR=2 python3 tests/test_programs.py --fuzz 150 > results/s23/k2_programs.log 2>&1; echo "k2programs $? $(tail -n 1 results/s23/k2_programs.log)" >> $L; fi
if step k2fuzz; then OMEGA_ILR=2 python3 tests/fuzz_rtl.py 0 600 --out /tmp/k2fz.jsonl > /tmp/k2fz.log 2>&1; tail -n 3 /tmp/k2fz.log > results/s23/k2_fuzz.log; echo "k2fuzz $(tail -n 1 results/s23/k2_fuzz.log)" >> $L; rm -f /tmp/k2fz.jsonl; fi
if step k2bigfuzz; then OMEGA_ILR=2 python3 tests/fuzz_rtl.py 0 200 --big --out /tmp/k2fzb.jsonl > /tmp/k2fzb.log 2>&1; tail -n 3 /tmp/k2fzb.log > results/s23/k2_bigfuzz.log; echo "k2bigfuzz $(tail -n 1 results/s23/k2_bigfuzz.log)" >> $L; rm -f /tmp/k2fzb.jsonl; fi
if step k1units; then OMEGA_ILR=1 python3 tests/test_units.py --rtl > results/s23/k1_units.log 2>&1; echo "k1units $? $(tail -n 1 results/s23/k1_units.log)" >> $L; fi
if step k1fuzz; then OMEGA_ILR=1 python3 tests/fuzz_rtl.py 0 600 --out /tmp/k1fz.jsonl > /tmp/k1fz.log 2>&1; tail -n 3 /tmp/k1fz.log > results/s23/k1_fuzz.log; echo "k1fuzz $(tail -n 1 results/s23/k1_fuzz.log)" >> $L; rm -f /tmp/k1fz.jsonl; fi
if step k1bigfuzz; then OMEGA_ILR=1 python3 tests/fuzz_rtl.py 0 200 --big --out /tmp/k1fzb.jsonl > /tmp/k1fzb.log 2>&1; tail -n 3 /tmp/k1fzb.log > results/s23/k1_bigfuzz.log; echo "k1bigfuzz $(tail -n 1 results/s23/k1_bigfuzz.log)" >> $L; rm -f /tmp/k1fzb.jsonl; fi
if step mutants; then python3 tests/mutants.py > results/mutants.txt 2>&1; tail -n 1 results/mutants.txt > results/mutants.log; echo "mutants $? $(tail -n 1 results/mutants.txt)" >> $L; fi
for i in 1 2; do
  if step b8_$i; then OMEGA_ILR=$i python3 bench/sweep14.py $P 8x8 2 8 results/s23/b8_ilr$i.jsonl > results/s23/b8_$i.log 2>&1; echo "b8_$i $? $(wc -l < results/s23/b8_ilr$i.jsonl)" >> $L; fi
done
echo ALLDONE >> $L
touch results/s23/reg.done
