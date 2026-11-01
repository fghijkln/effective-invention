# step 26: wait for the s26 mutants, then the full regression (serial; 2 cores shared with another project)
cd /workspace/work/omega
while [ ! -f results/s26/s26_mut.log.done ]; do sleep 30; done
bash results/s26/reg.sh > results/s26/reg.out 2>&1
