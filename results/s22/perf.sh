cd /workspace/work/omega; export PYTHONPATH=.:tests
while [ ! -f results/s22/cexv.log.done ]; do sleep 10; done
OMEGA_ADM=24 python3 results/s20/perf.py strict 1-20 t6,l20,f6,t9
OMEGA_ADM=8 python3 results/s20/perf.py lm8 1-20 t6,l20
python3 results/s20/perf.py dflt 1-20 t6,l20,f6
python3 results/s22/bench_id.py 4x4,8x8 > results/s22/bench_adm0.jsonl
OMEGA_ADM=24 python3 results/s22/bench_id.py 4x4,8x8 > results/s22/bench_adm24.jsonl
