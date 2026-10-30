cd /workspace/work
[ -f ~/env.sh ] || bash /workspace/work/setup_tc_noyosys.sh > /workspace/work/omega/results/s19/tc.log 2>&1
source ~/env.sh
cd /workspace/work/omega
export PYTHONPATH=.:tests PYTHONUNBUFFERED=1 OMEGA_SPLIT=800 OMEGA_JOBS=1
unset OMEGA_RTO OMEGA_RGRAD
ulimit -v 4500000
L=results/s19/reg.status
grep -q bigfuzz $L || { python3 tests/fuzz_rtl.py 0 200 --big --out /tmp/fzb.jsonl > /tmp/fzb.log 2>&1; tail -n 3 /tmp/fzb.log > results/fuzz_rtl_big.log; cp /tmp/fzb.jsonl results/fuzz_rtl_big.jsonl; echo "bigfuzz $(tail -n 1 results/fuzz_rtl_big.log)" >> $L; }
grep -q security $L || { python3 tests/test_security.py --fuzz 300 > results/security.log 2>&1; echo "security $? $(tail -n 1 results/security.log)" >> $L; }
grep -q mempress $L || { python3 tests/test_mempress.py > results/mempress.log 2>&1; echo "mempress $? $(tail -n 1 results/mempress.log)" >> $L; }
grep -q mutants $L || { python3 tests/mutants.py > results/mutants.txt 2>&1; tail -n 1 results/mutants.txt > results/mutants.log; echo "mutants $? $(tail -n 1 results/mutants.txt)" >> $L; }
echo ALLDONE >> $L
