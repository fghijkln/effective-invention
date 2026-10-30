# step 20: verification table header, mutant row, commits line (run after reg.status has ALLDONE)
import re
st={l.split()[0]:l.strip() for l in open('results/s20/reg.status') if l.strip() and l.split()[0]!='ALLDONE'}
def frac(k):
    m=re.search(r"(\d+)/(\d+)", st[k]); return m.group(1), m.group(2)
p='README.md'; s=open(p).read()
old="### Verification (full regression on step 19 = step 18 + the room-distance gradient, with the new defaults `+rto=8 +rgrad=3`:"
assert old in s
s=s.replace(old,"### Verification (full regression on step 20 = step 19 with slot reserve 1 (`+rsv=1`), defaults `+rto=8 +rgrad=3 +rsv=1`; step 19 = step 18 + the room-distance gradient:")
mp=frac('mempress'); mu=frac('mutants'); bf=frac('bigfuzz'); se=frac('security'); fz=frac('fuzz'); pr=frac('programs'); un=frac('units'); s14=frac('s14')
s=s.replace("| memory pressure (`tests/test_mempress.py`) | **44 / 44** |",f"| memory pressure (`tests/test_mempress.py`) | **{mp[0]} / {mp[1]}** |")
s=s.replace("| mutation testing (`tests/mutants.py`) | **51 / 51 caught** |",f"| mutation testing (`tests/mutants.py`) | **{mu[0]} / {mu[1]} caught** |")
old="50 full-cell pass-on off (global treesum(7) 8×8 seeds 16 / 18 stop at ~4,560 of 4,586 interactions) |"
assert old in s
s=s.replace(old,"50 full-cell pass-on off (global treesum(7) 8×8 seeds 16 / 18 stop at ~4,560 of 4,586 interactions) + 1 step-20 mutant: 51 slot reserve applied without a downhill neighbour (fib(10) on 1×1 with exactly the 93 free node / var slots its RTL run needs ends in status 2) |")
line=(f"* step 20: slot reserve 4 → 1 as run-time input `+rsv` / `OMEGA_RSV` (`+rsv=4` = step 19): RTL global pressure list(20) 3×2 −3.8%, fib(12) 6×6 −1.6%, "
      f"treesum(7) 8×8 −1.8%, no stopped run; treesum(6) 3×3 +3.7% vs step 18 traced and kept as a known gap; SPEC §7.1 progress argument with a counterexample "
      f"(no local mechanism can guarantee completion); fabric probe knobs; units {un[0]}/{un[1]}, programs {pr[0]}/{pr[1]}, step-14 cross-check {s14[0]}/{s14[1]}, "
      f"fuzz {fz[0]}/{fz[1]} + big {bf[0]}/{bf[1]}, security {se[0]}/{se[1]}, mempress {mp[0]}/{mp[1]}, mutants {mu[0]}/{mu[1]}, identity 128/128\n")
s=s.rstrip("\n")+"\n"+line
open(p,'w').write(s)
print(line)
