# Step 25 resume after sandbox restart (serial): setup, reg.sh (bigfuzz, security, mutA), mutb.sh (remaining 27-36), after.sh
[ -f ~/env.sh ] || bash /workspace/work/setup_tc_noyosys.sh > results/s25/setup2.log 2>&1
cd /workspace/work/omega
bash results/s25/reg.sh > results/s25/reg.out4 2>&1
bash results/s25/mutb.sh > results/s25/mutb.out2 2>&1
bash results/s25/after.sh > results/s25/after.out 2>&1
