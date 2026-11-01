#!/bin/bash
# usage: run.sh LOG args...   (step 28 tests in the worktree, detached)
cd /workspace/work/omega; source ~/env.sh; ulimit -v 4500000
export PYTHONPATH=.:tests OMEGA_SPLIT=400 OMEGA_JOBS=1 OMEGA_BUILD=/tmp/b_s28m PYTHONUNBUFFERED=1
LOG=$1; shift; rm -f $LOG.done
python3 tests/test_s28.py "$@" > $LOG 2>&1; echo EXIT $? >> $LOG.done
