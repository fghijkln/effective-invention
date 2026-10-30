source ~/env.sh
cd /workspace/work/omega
while ! grep -q IDDONE results/s19/id.log 2>/dev/null; do sleep 30; done
export PYTHONPATH=.:tests PYTHONUNBUFFERED=1 OMEGA_SPLIT=800 OMEGA_JOBS=1
unset OMEGA_RTO OMEGA_RGRAD
ulimit -v 4500000
L=results/s19/reg.status; : > $L
python3 tests/test_units.py --rtl > results/units_rtl.log 2>&1; echo "units $? $(tail -n 1 results/units_rtl.log)" >> $L
python3 tests/test_programs.py --fuzz 150 > results/programs.log 2>&1; echo "programs $? $(tail -n 1 results/programs.log)" >> $L
python3 tests/test_s14.py > results/s14_cross.log 2>&1; echo "s14 $? $(tail -n 1 results/s14_cross.log)" >> $L
python3 tests/fuzz_rtl.py 0 600 --out /tmp/fz.jsonl > /tmp/fz.log 2>&1; tail -n 3 /tmp/fz.log > results/fuzz_rtl.log; echo "fuzz $(tail -n 1 results/fuzz_rtl.log)" >> $L
python3 tests/fuzz_rtl.py 0 200 --big --out /tmp/fzb.jsonl > /tmp/fzb.log 2>&1; tail -n 3 /tmp/fzb.log > results/fuzz_rtl_big.log; echo "bigfuzz $(tail -n 1 results/fuzz_rtl_big.log)" >> $L
python3 tests/test_security.py --fuzz 300 > results/security.log 2>&1; echo "security $? $(tail -n 1 results/security.log)" >> $L
python3 tests/test_mempress.py > results/mempress.log 2>&1; echo "mempress $? $(tail -n 1 results/mempress.log)" >> $L
python3 tests/mutants.py > results/mutants.txt 2>&1; tail -n 1 results/mutants.txt > results/mutants.log; echo "mutants $? $(tail -n 1 results/mutants.txt)" >> $L
echo ALLDONE >> $L
