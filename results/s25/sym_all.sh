# Step 25: CLI output of the symbolic bound for the suite (+ sort worst / best case inputs, sort decomposition) and W_vars
cd /workspace/work/omega; export PYTHONPATH=.
for p in fib:22 sum:60 fact:60 list:60 higher:60 treesum:13 treesum_direct:15 sort:45; do python3 -m omega.eal --symbolic ${p%%:*} ${p##*:}; echo; done > results/s25/symbolic.log 2>&1
for f in desc asc; do python3 -m omega.eal --symbolic results/s25/sort_$f.olm 45; echo; done >> results/s25/symbolic.log 2>&1
python3 results/s25/sort_decomp.py 45 > results/s25/sort_decomp.log 2>&1
python3 -m omega.causal fib:10 sum:100 fact:12 list:25 sort:15 higher:30 treesum:6 treesum_direct:8 > results/s25/wvars.log 2>&1
