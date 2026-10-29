#!/bin/bash
ulimit -v 4500000
source ~/env.sh
cd /workspace/work/omega
export OMEGA_JOBS=1
python3 tests/test_programs.py
echo DONE rc=$?
