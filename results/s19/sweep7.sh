cd /workspace/work/omega
while ! grep -q ALLDONE results/s19/rtl12.err 2>/dev/null; do sleep 20; done
ulimit -v 1500000
export PYTHONPATH=.:tests
OMEGA_RTO=8 OMEGA_RGRAD=3 python3 results/s19/sw19.py rto8-g3-rsv4-fwd >> results/s19/sweep7.jsonl 2>>results/s19/sweep7.err
OMEGA_RTO=8 OMEGA_RGRAD=3 python3 results/s19/sw19b.py rto8-g3-rsv4-fwd 21 40 | tail -n 1 >> results/s19/sweep7.jsonl 2>>results/s19/sweep7.err
echo DONE >> results/s19/sweep7.jsonl
