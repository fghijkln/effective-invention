"""qsort_l / qsort sources with another input: seed s (same generator), ascending or descending (same template shape)."""
import re
def src(base, N, s=42, kind="rnd"):
    t = open(f"programs/{base}.olm").read()
    if kind == "asc": t = t.replace("(s * 1103515245 + 12345)", "(s * 1 + 1)"); s = 1
    if kind == "desc": t = t.replace("(s * 1103515245 + 12345)", "(s * 1 + 2147483647)"); s = N
    t = t.replace("rnd(N, 42)", f"rnd(N, {s})")
    return re.sub(r"\bN\b", str(N), t)
def data(N, s=42, kind="rnd"):
    if kind == "asc": return [(1 + i) % 100 for i in range(N)]
    if kind == "desc": return [(N - i) % 100 for i in range(N)]
    out = []
    for _ in range(N): out.append(s % 100); s = (s * 1103515245 + 12345) % 2147483648
    return out
