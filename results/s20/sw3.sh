cd /workspace/work/omega; ulimit -v 1500000
while ! grep -q DONE results/s20/sw2.jsonl 2>/dev/null; do sleep 10; done
for K in 130 160 200 300; do
  python3 results/s20/cex.py $K 1-20 >> results/s20/cex.jsonl
  OMEGA_RTO=32 OMEGA_RGRAD=0 python3 results/s20/cex.py $K 1-20 >> results/s20/cex.jsonl
done
echo DONE >> results/s20/cex.jsonl
