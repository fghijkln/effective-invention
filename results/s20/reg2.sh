# resume after sandbox restart at 15:00 UTC: mutants 0..30 finished (mutants_part1.txt); run 31..51 and combine
[ -f ~/env.sh ] || bash /workspace/work/setup_tc_noyosys.sh > /workspace/work/omega/results/s20/tc_setup2.log 2>&1
source ~/env.sh
cd /workspace/work/omega
export PYTHONPATH=.:tests PYTHONUNBUFFERED=1 OMEGA_SPLIT=800 OMEGA_JOBS=1
unset OMEGA_RTO OMEGA_RGRAD OMEGA_RSV
ulimit -v 4500000
L=results/s20/reg.status
python3 tests/mutants.py $(seq 31 51) > results/s20/mutants_part2.txt 2>&1
{ grep '^mutant ' results/s20/mutants_part1.txt; grep '^mutant ' results/s20/mutants_part2.txt; } > results/mutants.txt
n=$(grep -c '^mutant ' results/mutants.txt); c=$(grep -c '^mutant .. CAUGHT' results/mutants.txt)
echo "mutants: $c/$n caught" >> results/mutants.txt
tail -n 1 results/mutants.txt > results/mutants.log
echo "mutants $([ $c = $n ] && echo 0 || echo 1) $(tail -n 1 results/mutants.txt)" >> $L
echo ALLDONE >> $L
