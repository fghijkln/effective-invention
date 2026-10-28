#!/bin/bash
# Full regression: unit (semantic+fabric+RTL), programs (+150 random program cases), RTL fuzz
# (600 small + 200 big random nets), owner-capability security (+300 multi-tenant fuzz), memory pressure, mutants.  Logs in results/.
cd "$(dirname "$0")/.." && export PYTHONPATH=.:tests
set -o pipefail
python3 tests/test_units.py --rtl            2>&1 | tee results/units_rtl.log
python3 tests/test_programs.py --fuzz 150    2>&1 | tee results/programs.log
rm -f results/fuzz_rtl.jsonl results/fuzz_rtl_big.jsonl
python3 tests/fuzz_rtl.py 0 600 --out results/fuzz_rtl.jsonl       2>&1 | tail -3 | tee results/fuzz_rtl.log
python3 tests/fuzz_rtl.py 0 200 --big --out results/fuzz_rtl_big.jsonl 2>&1 | tail -3 | tee results/fuzz_rtl_big.log
python3 tests/test_security.py --fuzz 300    2>&1 | tee results/security.log
python3 tests/test_mempress.py               2>&1 | tee results/mempress.log
python3 tests/mutants.py                      2>&1 | tee results/mutants.txt
echo ALLDONE
