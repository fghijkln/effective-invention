#!/bin/bash
# step 13 gap: 8x8 sum/sort/higher/fact at default config (16,4,4,30), seeds 1-4
ulimit -v 4500000
source ~/env.sh
cd /workspace/work/omega
export OMEGA_SPLIT=800 OMEGA_JOBS=1
python3 bench/sweep13.py sum:1000,sort:20,higher:100,fact:20 8x8 "16,4,4,30" 4 results/s13_8x8_gap.jsonl
echo DONE rc=$?
