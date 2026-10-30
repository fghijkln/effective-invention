source ~/env.sh
cd /workspace/work/omega
while ! grep -q DONE results/s20/rtl3.status 2>/dev/null; do sleep 30; done
export PYTHONPATH=.:tests PYTHONUNBUFFERED=1 OMEGA_SPLIT=800 OMEGA_JOBS=1
unset OMEGA_RTO OMEGA_RGRAD OMEGA_RSV
ulimit -v 4500000
L=results/s20/reg.status
[ -f $L ] || : > $L
step(){ grep -q "^$1 " $L && return 1; return 0; }
if step mut51; then python3 tests/mutants.py 51 > results/s20/mut51.txt 2>&1; echo "mut51 $? $(tail -n 1 results/s20/mut51.txt)" >> $L; fi
P=qsort:40,list:120,sum:1000,sort:20,higher:100,fib:20,treesum:9,treesum_direct:14
if step id; then rm -f results/s20/id_4x4.jsonl results/s20/id_8x8.jsonl
  python3 bench/sweep14.py $P 4x4 2 8 results/s20/id_4x4.jsonl > results/s20/id.log 2>&1
  python3 bench/sweep14.py $P 8x8 2 8 results/s20/id_8x8.jsonl >> results/s20/id.log 2>&1
  sed 's#results/s19/id_#results/s20/id_#g; s#Step 19 identity check: default (+rto=8 +rgrad=3)#Step 20 identity check: default (+rto=8 +rgrad=3 +rsv=1)#' results/s19/idcmp.py > results/s20/idcmp.py
  python3 results/s20/idcmp.py > results/s20/idcmp.txt 2>&1; echo "id $(head -n 1 results/s20/idcmp.txt)" >> $L; fi
if step units; then python3 tests/test_units.py --rtl > results/units_rtl.log 2>&1; echo "units $? $(tail -n 1 results/units_rtl.log)" >> $L; fi
if step programs; then python3 tests/test_programs.py --fuzz 150 > results/programs.log 2>&1; echo "programs $? $(tail -n 1 results/programs.log)" >> $L; fi
if step s14; then python3 tests/test_s14.py > results/s14_cross.log 2>&1; echo "s14 $? $(tail -n 1 results/s14_cross.log)" >> $L; fi
if step fuzz; then python3 tests/fuzz_rtl.py 0 600 --out /tmp/fz.jsonl > /tmp/fz.log 2>&1; tail -n 3 /tmp/fz.log > results/fuzz_rtl.log; echo "fuzz $(tail -n 1 results/fuzz_rtl.log)" >> $L; fi
if step bigfuzz; then python3 tests/fuzz_rtl.py 0 200 --big --out /tmp/fzb.jsonl > /tmp/fzb.log 2>&1; tail -n 3 /tmp/fzb.log > results/fuzz_rtl_big.log; echo "bigfuzz $(tail -n 1 results/fuzz_rtl_big.log)" >> $L; fi
if step security; then python3 tests/test_security.py --fuzz 300 > results/security.log 2>&1; echo "security $? $(tail -n 1 results/security.log)" >> $L; fi
if step mempress; then python3 tests/test_mempress.py > results/mempress.log 2>&1; echo "mempress $? $(tail -n 1 results/mempress.log)" >> $L; fi
if step mutants; then python3 tests/mutants.py > results/mutants.txt 2>&1; tail -n 1 results/mutants.txt > results/mutants.log; echo "mutants $? $(tail -n 1 results/mutants.txt)" >> $L; fi
echo ALLDONE >> $L
