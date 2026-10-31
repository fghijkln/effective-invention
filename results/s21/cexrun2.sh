cd /workspace/work/omega; export PYTHONPATH=.:tests
run(){ echo "== $*"; env "$@" python3 results/s20/cex.py 200 1-20; }
for c in "$@"; do run $c; done
