#!/bin/bash
# Fast regression subset for CI (a few minutes): directed units on semantic+fabric+RTL,
# program suite (no random cases), 80 small random-net RTL differential cases.
set -euo pipefail
cd "$(dirname "$0")/.." && export PYTHONPATH=.:tests
python3 tests/test_units.py --rtl
python3 tests/test_programs.py --fuzz 0
python3 tests/fuzz_rtl.py 0 80
python3 tests/test_security.py --fuzz 20
python3 tests/test_mempress.py --quick
echo CI_QUICK_OK
