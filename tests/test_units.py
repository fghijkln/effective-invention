"""Directed tests: IR parser, every rule of the rule table, the frontend, and the fabric/RTL on the
same nets.  usage: test_units.py [--rtl]"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from omega import ir, semantic, fabric, lang
from omega.ports import *

ID = "@id = (a a)\n"
CASES = [
    # name, IR, expected readback, expected interactions
    ("anni_con", "@main = (a b) & (#1 #2) ~ (a b)", "(#1 #2)", 1),
    ("anni_dup_same_label", "@main = (a b) & {1 #3 #4} ~ {1 a b}", "(#3 #4)", 1),
    ("comm_dup_labels", "@main = (r s) & {1 #1 #2} ~ {2 r s}", "({1 #1 #2} {1 #1 #2})", 3),
    ("comm_con_dup", "@main = (r s) & (#1 #2) ~ {1 r s}", "((#1 #2) (#1 #2))", 3),
    ("erase_con", "@main = (a b) & * ~ (a b)", "(* *)", 1),
    ("erase_chain", "@main = r & * ~ ((a b) (a b)) & #5 ~ r", "#5", 5),
    ("num_copy_dup", "@main = (a b) & #7 ~ {1 a b}", "(#7 #7)", 1),
    ("num_copy_con", "@main = (a b) & #7 ~ (a b)", "(#7 #7)", 1),
    ("opr_direct", "@main = r & #10 ~ $(- #3 r)", "#7", 1),
    ("opr_flipped", "@main = r & #10 ~ $(-' #3 r)", "#4294967289", 1),
    ("opr_via_var", "@main = r & #10 ~ $(- a r) & a ~ #3", "#7", 2),
    ("opr_mul_wrap", "@main = r & #65536 ~ $(* #65536 r)", "#0", 1),
    ("opr_div0", "@main = r & #5 ~ $(/ #0 r)", "#0", 1),
    ("opr_cmp", "@main = (a b) & #3 ~ $(< #4 a) & #3 ~ $(>= #4 b)", "(#1 #0)", 2),
    ("opr_shift", "@main = r & #1 ~ $(<< #31 r)", "#2147483648", 1),
    ("swi_zero", "@main = r & #0 ~ ?((#5 #6) r)", "#5", 3),
    ("swi_succ", "@main = r & #4 ~ ?((#5 (p p)) r)", "#3", 4),
    ("ref_expand", ID + "@main = r & @id ~ (#9 r)", "#9", 2),
    ("ref_erase", ID + "@main = * & @id ~ *", "*", 1),
    ("ref_dup_copy", ID + "@main = (a b) & @id ~ {1 a b}", "(@id @id)", 1),
    ("ref_num", "@k = #4\n@main = r & @k ~ r & @k ~ #1", "@k", 2),
    ("void_nums", "@main = #1 & #2 ~ #3 & * ~ *", "#1", 2),
    ("var_chain", "@main = a & a ~ b & b ~ c & c ~ #8", "#8", 0),
    ("normal_form_lambda", "@main = (a a)", "(x0 x0)", 0),
    ("dup_lambda", "@main = (r s) & (x x) ~ {1 r s}", "((x0 x0) (x1 x1))", 2),
]

LANG = [
    ("let_and_dup", "def main = let x = 6 in x * x + x", 42),
    ("unused_var", "def k(a, b) = a\ndef main = k(3, 99)", 3),
    ("closure", "def add(a) = \\b -> a + b\ndef main = add(4)(5)", 9),
    ("nested_switch", "def f(n) = switch n { 0 => 10; p => switch p { 0 => 20; q => q } }\ndef main = f(0) + f(1) * 2 + f(7)", 55),
    ("if_chain", "def sgn(a, b) = if a < b then 1 else if a == b then 2 else 3\ndef main = sgn(1,2) * 100 + sgn(2,2) * 10 + sgn(3,2)", 123),
    ("church", "def two = \\f x -> f(f(x))\ndef main = two(two)(\\x -> x + 1)(0)", 4),
    ("ackermann", "def ack(m, n) = switch m { 0 => n + 1; p => switch n { 0 => ack(p, 1); q => ack(p, ack(m, q)) } }\ndef main = ack(2, 3)", 9),
    ("mutual", "def ev(n) = switch n { 0 => 1; p => od(p) }\ndef od(n) = switch n { 0 => 0; p => ev(p) }\ndef main = ev(10) * 10 + od(7)", 11),
    ("match_tree", "data T = L(v) | N(a, b)\ndef s(t) = match t { L(v) => v; N(a, b) => s(a) + s(b) }\ndef main = s(N(N(L(1), L(2)), L(4)))", 7),
    # step 6 frontend: nested / literal / default patterns, let
    ("nested_pattern", "data List = Nil | Cons(h, t)\n"
     "def pairs(xs) = match xs { Cons(a, Cons(b, t)) => a * b + pairs(t); _ => 0 }\n"
     "def main = pairs(Cons(1, Cons(2, Cons(3, Cons(4, Cons(5, Nil))))))", 14),
    ("number_patterns", "def f(n) = match n { 0 => 100; 1 => 200; k => k * 2 }\ndef main = f(0) + f(1) + f(7)", 314),
    ("default_and_binder", "data T = A | B(x) | C(x, y)\n"
     "def g(t) = match t { B(v) => v; other => match other { C(p, q) => p + q; _ => 1000 } }\n"
     "def main = g(A) + g(B(5)) + g(C(3, 4))", 1012),
    ("literal_in_ctor", "data List = Nil | Cons(h, t)\n"
     "def zeros(xs) = match xs { Cons(0, t) => 1 + zeros(t); Cons(_, t) => zeros(t); Nil => 0 }\n"
     "def main = zeros(Cons(0, Cons(3, Cons(0, Cons(0, Cons(5, Nil))))))", 3),
    ("pair_columns", "data B = T | F\ndata P = P(a, b)\n"
     "def both(p) = match p { P(T, T) => 1; P(_, _) => 0 }\n"
     "def swap(p) = match p { P(x, y) => P(y, x) }\n"
     "def main = let q = swap(P(3, 4)) in match q { P(a, b) => a * 10 + b + both(P(T, T)) * 100 + both(P(T, F)) * 1000 }", 143),
    ("polymorphic_helper", "data List = Nil | Cons(h, t)\n"
     "def len(xs) = match xs { Nil => 0; Cons(_, t) => 1 + len(t) }\n"
     "def map(f, xs) = match xs { Nil => Nil; Cons(h, t) => Cons(f(h), map(f, t)) }\n"
     "def main = len(map(\\x -> \\y -> x + y, Cons(1, Cons(2, Nil)))) + len(Cons(Nil, Nil))", 3),
]

# programs the frontend must reject (scope / pattern / type errors)
LANG_ERRORS = [
    ("unbound variable", "def main = x + 1"),
    ("constructor arity", "data List = Nil | Cons(h, t)\n" "def f(l) = match l { Cons(h) => h; Nil => 0 }\ndef main = f(Nil)"),
    ("non-exhaustive", "data List = Nil | Cons(h, t)\n" "def f(l) = match l { Cons(h, t) => h }\ndef main = f(Nil)"),
    ("redundant arm", "data List = Nil | Cons(h, t)\n" "def f(l) = match l { _ => 0; Nil => 1 }\ndef main = f(Nil)"),
    ("binder twice", "data List = Nil | Cons(h, t)\n" "def f(l) = match l { Cons(x, x) => x; Nil => 0 }\ndef main = f(Nil)"),
    ("unknown constructor", "data List = Nil | Cons(h, t)\n" "def f(l) = match l { Cons(h, t) => h; Nill(q) => 0 }\ndef main = f(Nil)"),
    ("duplicate parameter", "def f(a, a) = a\ndef main = f(1, 2)"),
    ("data in arithmetic", "data List = Nil | Cons(h, t)\n" "def main = 1 + Nil"),
    ("match on a number", "data List = Nil | Cons(h, t)\n" "def main = match 5 { Nil => 0; Cons(h, t) => h }"),
    ("apply a number", "def main = 3(4)"),
    ("if arms disagree", "data List = Nil | Cons(h, t)\n" "def main = if 1 then Nil else 0"),
    ("condition is data", "data List = Nil | Cons(h, t)\n" "def main = if Nil then 1 else 0"),
    ("wrong argument kind", "data List = Nil | Cons(h, t)\n" "def len(xs) = match xs { Nil => 0; Cons(_, t) => 1 + len(t) }\ndef main = len(7)"),
    ("main is a function", "def main = \\x -> x"),
    ("mixed pattern kinds", "data List = Nil | Cons(h, t)\n" "def f(l) = match l { Nil => 0; 3 => 1 }\ndef main = f(Nil)"),
]


def check_net(name, book, want, want_i, use_rtl, shapes):
    fails = 0
    r = semantic.result(book, seed=1)
    for order in ("lifo", "fifo"):
        r2 = semantic.result(book, order=order)
        assert (r2["readback"], r2["interactions"], r2["nodes"]) == (r["readback"], r["interactions"], r["nodes"]), name
    if want is not None and r["readback"] != want:
        print(f"FAIL {name}: semantic readback {r['readback']} want {want}"); fails += 1
    if want_i is not None and r["interactions"] != want_i:
        print(f"FAIL {name}: semantic interactions {r['interactions']} want {want_i}"); fails += 1
    for W, H in shapes:
        f = fabric.Fabric(book, W, H, seed=W * 7 + H, p_jitter=0.2, p_stall=0.1,
                          img=fabric.Image(book, W, H, 1024, 1024, scatter=W + H)).run()
        got = (f.readback(), f.interactions, f.node_count())
        if got != (r["readback"], r["interactions"], r["nodes"]):
            print(f"FAIL {name}: fabric {W}x{H} {got}"); fails += 1
        if use_rtl:
            from omega import rtl
            x = rtl.run(book, W, H, seed=W * 13 + H, jitter=40, stall=20,
                        img=fabric.Image(book, W, H, 1024, 1024, scatter=W + H))
            got = (x["readback"], x["interactions"], x["node_count"])
            if got != (r["readback"], r["interactions"], r["nodes"]):
                print(f"FAIL {name}: rtl {W}x{H} {got}"); fails += 1
    return fails


def main():
    use_rtl = "--rtl" in sys.argv
    shapes = [(1, 1), (2, 2), (4, 4)]
    n = fails = 0
    # parser round trip
    for _, src, _, _ in CASES:
        b = ir.parse_book(src)
        b2 = ir.parse_book(b.to_text())
        assert b2.to_text() == b.to_text()
    n += 1
    for name, src, want, wi in CASES:
        n += 1
        fails += check_net(name, ir.parse_book(src), want, wi, use_rtl, shapes)
    for name, src, want in LANG:
        n += 1
        fails += check_net(name, lang.compile_book(src), f"#{want}", None, use_rtl, shapes)
    n += 1
    for name, src in LANG_ERRORS:
        try:
            lang.compile_book(src)
        except (SyntaxError, TypeError):
            continue
        print(f"FAIL frontend accepted a bad program ({name})"); fails += 1; break
    print(f"unit tests: {n - fails}/{n} pass" + (" (semantic + fabric + RTL 1x1/2x2/4x4)" if use_rtl else " (semantic + fabric)"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
