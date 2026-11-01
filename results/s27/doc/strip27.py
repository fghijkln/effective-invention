"""Write step-26-only README.md / SPEC.md / tests/ci_quick.sh to OUTDIR (the working tree holds steps 26 + 27)."""
import sys
R = '/workspace/work/omega/'; O = sys.argv[1]
rd = open(R + 'README.md').read()
i = rd.index("### Quicksort in Ω-L (step 27)"); j = rd.index("### Memory-bound admission control in the RTL (step 26)")
rd = rd[:i] + rd[j:]
a = "### Verification (full regression on step 27 = step 26 + `programs/qsort_l.olm`, quicksort in Ω-L (new program and tests only); step 26 = "
assert a in rd; rd = rd.replace(a, "### Verification (full regression on step 26 = ")
for a, b in [("python3 tests/test_s27.py                # quicksort in Ω-L: bounds, closed forms, RTL at exactly B (step 27)\n", ""),
             ("; `qsort_l.olm`: quicksort in Ω-L (step 27) |", " |"),
             ("Ω-L\n    rejects `qsort.olm` (it duplicates a list; step 27's rewrite `qsort_l.olm` is in Ω-L, but 32–36% slower on a 2×2 mesh),", "Ω-L\n    rejects qsort (it duplicates a list),")]:
    assert a in rd, a; rd = rd.replace(a, b)
k = rd.index("| quicksort in Ω-L (`tests/test_s27.py`, step 27) |"); e = rd.index("\n", k); rd = rd[:k] + rd[e + 1:]
k = rd.index("* step 27: quicksort in Ω-L"); e = rd.index("\n", k); rd = rd[:k] + rd[e + 1:]
a = "a sized-type derivation of B(N) that needs no counting runs;"
assert a in rd; rd = rd.replace(a, "a sized-type derivation of B(N) that needs no counting runs, and an Ω-L variant that admits qsort (a `!`-list with a copy cost);")
open(O + '/README.md', 'w').write(rd)
sp = open(R + 'SPEC.md').read()
i = sp.index("### 7.6 Quicksort in Ω-L (step 27"); j = sp.index("## 8. Termination detection")
open(O + '/SPEC.md', 'w').write(sp[:i] + sp[j:])
ci = open(R + 'tests/ci_quick.sh').read().replace("python3 tests/test_s27.py --quick --no-rtl\n", "")
open(O + '/ci_quick.sh', 'w').write(ci)
print("ok")
