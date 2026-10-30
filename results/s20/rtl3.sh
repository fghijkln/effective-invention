source ~/env.sh; cd /workspace/work/omega; ulimit -v 4500000; export OMEGA_JOBS=1 PYTHONPATH=.:tests OMEGA_SPLIT=800
while pgrep -f "rtl2.sh" > /dev/null; do sleep 10; done
echo "6x6 start $(date)" > results/s20/rtl3.status
OMEGA_RSV=1 python3 results/s20/rtl_big.py 1 13 5 6 >> results/s20/rtl1.jsonl 2>>results/s20/rtl3.err
echo "8x8 start $(date)" >> results/s20/rtl3.status
OMEGA_RSV=1 python3 results/s20/rtl_big.py 1 30 7 >> results/s20/rtl1.jsonl 2>>results/s20/rtl3.err
echo "DONE $(date)" >> results/s20/rtl3.status
