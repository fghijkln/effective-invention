# Step 25 resume #3 (sandbox restart during mutb): setup, mutb.sh (remaining of 27-36), after.sh
[ -f ~/env.sh ] || bash /workspace/work/setup_tc_noyosys.sh > results/s25/setup3.log 2>&1
cd /workspace/work/omega
bash results/s25/mutb.sh > results/s25/mutb.out3 2>&1
bash results/s25/after.sh > results/s25/after.out 2>&1
