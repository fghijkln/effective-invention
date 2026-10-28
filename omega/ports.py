"""TACHYON-Omega port / node encoding (shared by every model, the loader and the RTL).

A *port* is a 64-bit word:

    [63:60] tag      NONE VAR REF ERA NUM CON DUP OPR SWI
    [59:44] label    DUP label | OPR {s,op} | REF definition id
    [43:40] owner    owner capability id (security demo; 0 = default program)
    [39:32] reserved (0)
    [31:0]  payload  NUM: 32-bit unsigned value
                     VAR / CON / DUP / OPR / SWI: address {x[23:20], y[19:16], slot[11:0]}

A *node* occupies one 128-bit slot = {aux2[127:64], aux1[63:0]}.  Its principal port is implicit:
whoever holds a pointer port (CON/DUP/OPR/SWI + address) is connected to that node's principal.
A *var* occupies one 64-bit var slot holding its substitution (NONE = not yet substituted).
"""

NONE, VAR, REF, ERA, NUM, CON, DUP, OPR, SWI = range(9)
ABS = 15                 # parser-only tree kind (absolute pointer); never a port tag
ABS_BIT = 1 << 39        # template-only flag: payload is an absolute address, do not relocate
OWNER_FREE = 15          # shadow owner tag of a free node/var slot (no tenant may use id 15)
CAP_TAGS = (VAR, REF, CON, DUP, OPR, SWI)   # ports that are capabilities (carry an owner)
TRAP_NONE, TRAP_CROSS, TRAP_FORGED, TRAP_OOB = 0, 1, 2, 3
TRAP_NAMES = ["none", "cross-owner", "forged-tag", "out-of-bounds"]
TAG_NAMES = ["NONE", "VAR", "REF", "ERA", "NUM", "CON", "DUP", "OPR", "SWI"]
NODE_TAGS = (CON, DUP, OPR, SWI)
M32 = 0xFFFFFFFF
M64 = (1 << 64) - 1

# OPR label = s << 4 | op
OPS = ["+", "-", "*", "/", "%", "==", "!=", "<", ">", "<=", ">=", "&", "|", "^", "<<", ">>"]
OP_ID = {o: i for i, o in enumerate(OPS)}


def mk(tag, label=0, payload=0, owner=0):
    return (tag << 60) | ((label & 0xFFFF) << 44) | ((owner & 0xF) << 40) | (payload & M32)


def tag(p):
    return (p >> 60) & 0xF


def label(p):
    return (p >> 44) & 0xFFFF


def owner(p):
    return (p >> 40) & 0xF


def is_cap(p):
    return tag(p) in CAP_TAGS


def with_owner(p, o):
    return (p & ~(0xF << 40) & M64) | ((o & 0xF) << 40)


def stamp(p, o):
    """Owner stamping on load / expansion: capabilities get the tenant's owner, atoms get 0."""
    p &= ~ABS_BIT & M64
    return with_owner(p, o if is_cap(p) else 0)


def payload(p):
    return p & M32


def with_payload(p, pl):
    return (p & ~M32 & M64) | (pl & M32)


def is_node(p):
    return tag(p) in NODE_TAGS


def is_var(p):
    return tag(p) == VAR


def addr(x, y, slot):
    return ((x & 0xF) << 20) | ((y & 0xF) << 16) | (slot & 0xFFF)


def addr_xy(a):
    return (a >> 20) & 0xF, (a >> 16) & 0xF


def addr_slot(a):
    return a & 0xFFF


ERA_P = mk(ERA)


def num(v):
    return mk(NUM, 0, v & M32)


def apply_op(op, a, b):
    a &= M32
    b &= M32
    if op == 0: r = a + b
    elif op == 1: r = a - b
    elif op == 2: r = a * b
    elif op == 3: r = a // b if b else 0
    elif op == 4: r = a % b if b else 0
    elif op == 5: r = int(a == b)
    elif op == 6: r = int(a != b)
    elif op == 7: r = int(a < b)
    elif op == 8: r = int(a > b)
    elif op == 9: r = int(a <= b)
    elif op == 10: r = int(a >= b)
    elif op == 11: r = a & b
    elif op == 12: r = a | b
    elif op == 13: r = a ^ b
    elif op == 14: r = a << (b & 31)
    else: r = a >> (b & 31)
    return r & M32


def show_port(p):
    t = tag(p)
    if t == NUM: return f"#{payload(p)}"
    if t == ERA: return "*"
    if t == NONE: return "_"
    if t == REF: return f"@{label(p)}"
    return f"{TAG_NAMES[t]}[{label(p)}]:{payload(p):#x}"
