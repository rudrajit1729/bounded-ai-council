"""
Worked mini-example for Appendix B (reliability computation).

Three coders (A, B, C), six units (u1..u6), two codes (X, Y). The functions
binary_matrix, krippendorff_binary, cohen_kappa, agreement, consensus_codes and
describe follow the reference implementation used in the authors' earlier studies;
pair_table matches pipeline/reliability.py, which adds the 2x2 counts and positive
and negative agreement. Standard library only. Run:  python3 supplement/b_example.py
"""
from __future__ import annotations

import math
from collections import OrderedDict
from itertools import combinations

CONSENSUS = 2          # a code sticks when at least this many coders apply it
ISSUE = "ISSUE"


# ----------------------------------------------------------------------------- agreement.py
def binary_matrix(long_rows, code, coders):
    """
    unit -> [1/0/None per coder], 1 if that coder applied `code` to that response.

    None means the coder never saw the unit, which is different from applying nothing.
    Keeping the distinction matters: alpha counts pairable values, so a unit one coder
    skipped still contributes through the pairs that do exist.
    """
    seen = {}
    for r in long_rows:
        seen.setdefault(r["pid"], {})[r["coder"]] = 1 if code in r["codes"] else 0
    return OrderedDict((pid, [row.get(c) for c in coders]) for pid, row in sorted(seen.items()))


def krippendorff_binary(matrix) -> float:
    """
    Krippendorff's alpha for a binary, fully-crossed design, from the coincidence matrix.

    Returns nan where alpha is undefined -- every coder used one value on every unit.
    Agreement is then perfect, but reporting 1.0 would overclaim: there was no variation
    to disagree about.
    """
    o = [[0.0, 0.0], [0.0, 0.0]]
    for vals in matrix.values():
        r = [v for v in vals if v is not None]
        n_u = len(r)
        if n_u < 2:
            continue
        for a in (0, 1):
            for b in (0, 1):
                pairs = sum(1 for x in r for y in r if x == a and y == b)
                if a == b:
                    pairs -= sum(1 for x in r if x == a)
                o[a][b] += pairs / (n_u - 1)
    n = o[0][0] + o[0][1] + o[1][0] + o[1][1]
    if n == 0:
        return float("nan")
    n0 = o[0][0] + o[0][1]
    n1 = o[1][0] + o[1][1]
    do = (o[0][1] + o[1][0]) / n
    if n <= 1:
        return float("nan")
    de = (2.0 * n0 * n1) / (n * (n - 1))
    if not de:
        return float("nan")
    return 1.0 - do / de


def cohen_kappa(x, y) -> float:
    pairs = [(a, b) for a, b in zip(x, y) if a is not None and b is not None]
    if not pairs:
        return float("nan")
    n = len(pairs)
    po = sum(1 for a, b in pairs if a == b) / n
    mx = sum(a for a, _ in pairs) / n
    my = sum(b for _, b in pairs) / n
    pe = mx * my + (1 - mx) * (1 - my)
    if pe >= 1.0:
        return float("nan")
    return (po - pe) / (1 - pe)


def agreement(long_rows, codes, coders):
    """One row per code: alpha, the pairwise kappas, and how often it was used."""
    out = []
    for code in codes:
        m = binary_matrix(long_rows, code, coders)
        cols = {c: [vals[i] for vals in m.values()] for i, c in enumerate(coders)}
        kappas = OrderedDict(("kappa_%s%s" % (a, b), cohen_kappa(cols[a], cols[b]))
                             for a, b in combinations(coders, 2))
        applied = [sum(1 for v in vals if v == 1) for vals in m.values()]
        ks = [v for v in kappas.values() if not math.isnan(v)]
        out.append(OrderedDict([
            ("code", code),
            ("alpha", krippendorff_binary(m)),
            *kappas.items(),
            ("kappa_mean", sum(ks) / len(ks) if ks else float("nan")),
            ("n_any", sum(1 for a in applied if a >= 1)),
            ("n_consensus", sum(1 for a in applied if a >= CONSENSUS)),
            ("n_unanimous", sum(1 for a in applied if a == len(coders))),
        ]))
    return sorted(out, key=lambda r: -r["n_consensus"])


def consensus_codes(long_rows):
    """The surviving coding: (pid, code, n_coders, unanimous) where >= CONSENSUS agreed."""
    tally = {}
    for r in long_rows:
        for c in r["codes"]:
            tally.setdefault((r["pid"], c), set()).add(r["coder"])
    n_coders = len({r["coder"] for r in long_rows})
    return [OrderedDict([("pid", pid), ("code", code), ("n_coders", len(cs)),
                         ("unanimous", len(cs) == n_coders)])
            for (pid, code), cs in sorted(tally.items()) if len(cs) >= CONSENSUS]


def describe(rel) -> str:
    a = sorted(r["alpha"] for r in rel if not math.isnan(r["alpha"]))
    if not a:
        return "no code had enough variation to compute agreement on"
    return ("%d codes; alpha median %.2f, range %.2f-%.2f; %d below 0.67, %d at or above 0.80"
            % (len(rel), a[len(a) // 2], a[0], a[-1],
               sum(1 for x in a if x < 0.67), sum(1 for x in a if x >= 0.80)))


# ----------------------------------------------------------------------------- pipeline/reliability.py
def pair_table(x, y):
    """2x2 counts for a coder pair on one code: a=both yes, b=x yes/y no, c=x no/y yes, d=both no."""
    a = b = c = d = 0
    for p, q in zip(x, y):
        if p is None or q is None:
            continue
        if p and q:
            a += 1
        elif p and not q:
            b += 1
        elif q and not p:
            c += 1
        else:
            d += 1
    n = a + b + c + d
    po = (a + d) / n if n else float("nan")
    pa = 2 * a / (2 * a + b + c) if (2 * a + b + c) else float("nan")
    na = 2 * d / (2 * d + b + c) if (2 * d + b + c) else float("nan")
    return OrderedDict([("a", a), ("b", b), ("c", c), ("d", d), ("raw", po), ("pos_agree", pa), ("neg_agree", na)])


# ----------------------------------------------------------------------------- the example
CODERS = ["A", "B", "C"]
CODES = ["X", "Y"]

# The assignment table from Appendix B, section B.9, as long rows (one row per coder per unit).
ASSIGNMENTS = {
    # unit: {coder: set of codes applied}
    "u1": {"A": {"X"},      "B": {"X"},      "C": {"X"}},
    "u2": {"A": {"X", "Y"}, "B": {"X", "Y"}, "C": {"Y"}},
    "u3": {"A": {"Y"},      "B": {"Y"},      "C": {"Y"}},
    "u4": {"A": {"X"},      "B": set(),      "C": {"X", "Y"}},
    "u5": {"A": set(),      "B": set(),      "C": set()},
    "u6": {"A": {"Y"},      "B": {"X", "Y"}, "C": {"Y"}},
}
LONG_ROWS = [{"pid": u, "coder": c, "codes": sorted(cs)}
             for u, row in ASSIGNMENTS.items() for c, cs in row.items()]


def coincidence(matrix):
    """Print the coincidence matrix the way krippendorff_binary builds it, unit by unit."""
    o = [[0.0, 0.0], [0.0, 0.0]]
    print("    unit  values      n_u   +o00  +o01  +o10  +o11")
    for pid, vals in matrix.items():
        r = [v for v in vals if v is not None]
        n_u = len(r)
        add = [[0.0, 0.0], [0.0, 0.0]]
        if n_u >= 2:
            for a in (0, 1):
                for b in (0, 1):
                    pairs = sum(1 for x in r for y in r if x == a and y == b)
                    if a == b:
                        pairs -= sum(1 for x in r if x == a)
                    add[a][b] = pairs / (n_u - 1)
        for a in (0, 1):
            for b in (0, 1):
                o[a][b] += add[a][b]
        print("    %-5s %-11s %d   %5.2f %5.2f %5.2f %5.2f"
              % (pid, str([v if v is not None else "-" for v in vals]).replace("'", ""), n_u,
                 add[0][0], add[0][1], add[1][0], add[1][1]))
    n = sum(o[0]) + sum(o[1])
    n0, n1 = sum(o[0]), sum(o[1])
    do = (o[0][1] + o[1][0]) / n if n else float("nan")
    de = (2.0 * n0 * n1) / (n * (n - 1)) if n > 1 else float("nan")
    print("    totals: o00=%.2f o01=%.2f o10=%.2f o11=%.2f  n=%.0f  n0=%.0f  n1=%.0f" % (o[0][0], o[0][1], o[1][0], o[1][1], n, n0, n1))
    print("    D_o = (o01+o10)/n = %.4f   D_e = 2*n0*n1/(n(n-1)) = %.4f   alpha = 1 - D_o/D_e = %.4f"
          % (do, de, 1 - do / de if de else float("nan")))


def fmt(v):
    return "nan" if isinstance(v, float) and math.isnan(v) else ("%.4f" % v if isinstance(v, float) else str(v))


def main():
    print("== Assignment table (1 = code applied) ==")
    for code in CODES:
        m = binary_matrix(LONG_ROWS, code, CODERS)
        print("  code %s: " % code + "  ".join("%s=%s" % (pid, "".join(str(v) for v in vals)) for pid, vals in m.items()))

    for code in CODES:
        print("\n== Code %s: binary matrix and coincidence matrix ==" % code)
        m = binary_matrix(LONG_ROWS, code, CODERS)
        coincidence(m)
        print("    krippendorff_binary -> %s" % fmt(krippendorff_binary(m)))
        cols = {c: [vals[i] for vals in m.values()] for i, c in enumerate(CODERS)}
        for a, b in combinations(CODERS, 2):
            t = pair_table(cols[a], cols[b])
            pairs = [(p, q) for p, q in zip(cols[a], cols[b])]
            n = len(pairs)
            po = sum(1 for p, q in pairs if p == q) / n
            mx = sum(p for p, _ in pairs) / n
            my = sum(q for _, q in pairs) / n
            pe = mx * my + (1 - mx) * (1 - my)
            print("    pair %s%s: a=%d b=%d c=%d d=%d | p_o=%.4f  m_%s=%.4f  m_%s=%.4f  p_e=%.4f  kappa=%s | PA=%s NA=%s"
                  % (a, b, t["a"], t["b"], t["c"], t["d"], po, a, mx, b, my, pe,
                     fmt(cohen_kappa(cols[a], cols[b])), fmt(t["pos_agree"]), fmt(t["neg_agree"])))

    print("\n== agreement(long_rows, codes, coders) ==")
    rel = agreement(LONG_ROWS, CODES, CODERS)
    for row in rel:
        print("  " + ", ".join("%s=%s" % (k, fmt(v)) for k, v in row.items()))
    print("  describe -> " + describe(rel))

    print("\n== consensus_codes(long_rows) ==")
    cons = consensus_codes(LONG_ROWS)
    for c in cons:
        print("  %s %s n_coders=%d unanimous=%s" % (c["pid"], c["code"], c["n_coders"], c["unanimous"]))
    n_any = sum(r["n_any"] for r in rel)
    n_cons = sum(r["n_consensus"] for r in rel)
    per_coder = sum(len(r["codes"]) for r in LONG_ROWS)
    print("  any-coder (unit, code) pairs = %d; consensus pairs = %d; survival = %d/%d = %.4f"
          % (n_any, n_cons, n_cons, n_any, n_cons / n_any))
    print("  (for contrast, per-coder assignment count = %d; consensus x 3 / that is not the survival rate reported)" % per_coder)

    print("\n== Missing-value convention: coder C never saw u6 (None, not 0) ==")
    rows = [r for r in LONG_ROWS if not (r["pid"] == "u6" and r["coder"] == "C")]
    m = binary_matrix(rows, "X", CODERS)
    coincidence(m)
    print("    krippendorff_binary -> %s" % fmt(krippendorff_binary(m)))
    cols = {c: [vals[i] for vals in m.values()] for i, c in enumerate(CODERS)}
    for a, b in combinations(CODERS, 2):
        t = pair_table(cols[a], cols[b])
        print("    pair %s%s: n_pairable=%d kappa=%s PA=%s NA=%s"
              % (a, b, t["a"] + t["b"] + t["c"] + t["d"], fmt(cohen_kappa(cols[a], cols[b])), fmt(t["pos_agree"]), fmt(t["neg_agree"])))

    print("\n== When alpha is undefined ==")
    never = OrderedDict((u, [0, 0, 0]) for u in ASSIGNMENTS)
    always = OrderedDict((u, [1, 1, 1]) for u in ASSIGNMENTS)
    print("  no coder ever applied the code:   alpha = %s, kappa_AB = %s"
          % (fmt(krippendorff_binary(never)), fmt(cohen_kappa([0] * 6, [0] * 6))))
    print("  every coder applied it everywhere: alpha = %s, kappa_AB = %s"
          % (fmt(krippendorff_binary(always)), fmt(cohen_kappa([1] * 6, [1] * 6))))
    print("  one coder constant, the other not: kappa = %s (p_e < 1, so defined)"
          % fmt(cohen_kappa([0] * 6, [0, 1, 0, 1, 0, 0])))


if __name__ == "__main__":
    main()
