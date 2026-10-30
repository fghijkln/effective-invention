cd /workspace/work/omega; ulimit -v 1500000
while ! grep -q DONE results/s20/sw1.jsonl; do sleep 10; done
r(){ tag=$1; shift; env "$@" python3 results/s20/perf.py $tag 1-20 t6,l20,f6,t9 >> results/s20/sw2.jsonl; }
r rsvi1 OMEGA_RSVI=1
r rg1f1 OMEGA_RG1F=1
r rg1d2 OMEGA_RG1D=2
r rsvd2 OMEGA_RSVD=2
r rsvi1rg1f1 OMEGA_RSVI=1 OMEGA_RG1F=1
r rsv0rg1d2 OMEGA_RSV=0 OMEGA_RG1D=2
r rsvd2rg1d2 OMEGA_RSVD=2 OMEGA_RG1D=2
echo DONE >> results/s20/sw2.jsonl
