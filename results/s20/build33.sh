source ~/env.sh; cd /workspace/work/omega; ulimit -v 4500000; export OMEGA_JOBS=1 PYTHONPATH=.:tests
python3 -c "
from omega import rtl
for W,H in [(3,3),(3,2)]: print(rtl.build(W,H,quiet=True))
" > results/s20/build33.log 2>&1; echo EXIT $? >> results/s20/build33.log
