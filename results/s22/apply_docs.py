"""Apply the step-22 README / SPEC text to the main tree (run from /workspace/work/omega)."""
import re, sys
R = open('README.md').read(); S = open('SPEC.md').read()

def rep(t, a, b, n=1):
    assert t.count(a) == n, (a[:80], t.count(a)); return t.replace(a, b)

# verification heading
R = rep(R, '### Verification (full regression on step 21 = step 20 + the keep-0 pressure cases (tests only);',
        '### Verification (full regression on step 22 = step 21 + low-memory watermarks (`+lm=2`, default; `+lm=0` = step 21 cycle for cycle); step 21 = step 20 + the keep-0 pressure cases (tests only);')
# mempress row
R = rep(R, '| memory pressure (`tests/test_mempress.py`) | **54 / 54** |', '| memory pressure (`tests/test_mempress.py`) | **56 / 56** |')
R = rep(R, '+ **the near-overfull global treesum(9) 3×3 (step 19)**,',
        '+ **the near-overfull global treesum(9) 3×3 (step 19)** + **near-overfull treesum(9) 3×3 with 500 free slots in the corner (step 22: fabric seed 14, RTL seed 9 stop at `+lm=0`)**,')
# mutants row
R = rep(R, '| mutation testing (`tests/mutants.py`) | **52 / 52 caught** |', '| mutation testing (`tests/mutants.py`) | **53 / 53 caught** |')
R = rep(R, 'ends in status 2) |', 'ends in status 2) + 1 step-22 mutant: 52 low-memory watermarks never engage (caught by the near-overfull treesum(9) 3×3 corner-500 case, RTL seed 9 stops with status 3) |')
# new section before step 21's
sec = open('results/s22/readme_s22.md').read().rstrip() + '\n\n'
R = rep(R, '### A default-configuration test for the full-cell pass-on (step 21)', sec + '### A default-configuration test for the full-cell pass-on (step 21)')
# known gaps
R = rep(R, 'fragments the memory until no pending SPAWN fits anywhere.',
        'fragments the memory until no pending SPAWN fits anywhere. Step 22\'s low-memory watermarks (`+lm=2`) make that case and its RTL counterpart finish, but they are still no guarantee (a depth-first order needing more than any one cell has, or memory spread thinner than 64 slots per cell, can stop, status 3), and they cost list(20) 3×2 under global pressure +3.9% on RTL (step 20\'s gain there given back).')
# next steps
R = rep(R, '3. Global memory pressure: a completion guarantee needs memory-aware admission, not re-routing (SPEC §7.1,\n   step 20 counterexample): e.g. a global low-memory signal (an OR tree like the quiescence tree) that makes\n   every cell stop giving work away and reduce depth first, bounding the peak by the sequential one, or\n   spilling to off-fabric memory.',
        '3. Global memory pressure: step 22\'s low-memory watermarks fix the step-20 counterexample but give no\n   guarantee (SPEC §7.1); a guarantee still needs bounding the peak by the sequential one (e.g. no gives at all\n   once memory is low, which step 22 found the no-room forwarding path undoes) or spilling to off-fabric memory.')
open('README.md', 'w').write(R)

# SPEC: §5 bullet after the gradient bullet, and §7.1 item 4
b = open('results/s22/spec_s22.md').read()
S = rep(S, '  timeout alone livelocked the fabric and the RTL under global pressure; the gradient removes that).\n',
        '  timeout alone livelocked the fabric and the RTL under global pressure; the gradient removes that).\n' + b)
S = rep(S, '   memory is detected (status 3 / "no progress"), never silently wrong.\n', open('results/s22/spec_s22_71.md').read())
open('SPEC.md', 'w').write(S)
print('ok')
