#!/usr/bin/env python3
"""
Stage 5: consensus, per-code reliability, survival, and the drop rule.

  consensus      a code is assigned to a unit when at least `thresholds.consensus` (2) coders assign it
  issue units    a unit two coders flag with an issue code is excluded from prevalence but kept in the file
  reliability    per code, on the binary decision: Krippendorff's alpha, pairwise Cohen's kappa with the
                 2x2 table, raw / positive / negative agreement, three-rater agreement; the mean kappa
                 over coder pairs from different families is reported separately
  distribution   median, minimum, maximum, number below 0.67, number at or above 0.80; no interval on
                 the median
  drop rule      codes with alpha below `thresholds.alpha_drop` (0.67) on the reliability units are
                 dropped from the results and listed, with definitions and agreement counts, for the
                 supplement; codes whose alpha is undefined (no variation) are listed beside them
  survival       share of (unit, code) pairs proposed by at least one coder that at least two assign

Standard library only.
"""
from __future__ import annotations

import csv
import json
import math
from collections import OrderedDict, defaultdict
from itertools import combinations
from pathlib import Path

UNCOVERED = "UNCOVERED"


def nan(x) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


def median(xs):
    xs = sorted(x for x in xs if not nan(x))
    if not xs:
        return None
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2.0


def pct(n, base):
    return round(100.0 * n / base, 1) if base else 0.0


def krippendorff_binary(matrix) -> float:
    """Krippendorff's alpha for one binary variable; matrix: unit -> [value per coder or None]."""
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
    n = sum(o[0]) + sum(o[1])
    if n <= 1:
        return float("nan")
    n0, n1 = sum(o[0]), sum(o[1])
    do = (o[0][1] + o[1][0]) / n
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


def pair_table(x, y):
    """2x2 counts for a coder pair on one code: a=both yes, b=x yes/y no, c=x no/y yes, d=both no."""
    a = b = c = d = 0
    for p, q in zip(x, y):
        if p is None or q is None:
            continue
        if p and q:
            a += 1
        elif p:
            b += 1
        elif q:
            c += 1
        else:
            d += 1
    n = a + b + c + d
    return OrderedDict([("a", a), ("b", b), ("c", c), ("d", d),
                        ("raw", (a + d) / n if n else float("nan")),
                        ("pos_agree", 2 * a / (2 * a + b + c) if (2 * a + b + c) else float("nan")),
                        ("neg_agree", 2 * d / (2 * d + b + c) if (2 * d + b + c) else float("nan"))])


def binary_matrix(rows, code, coders, units):
    seen = defaultdict(dict)
    uset = set(units)
    for r in rows:
        if r["uid"] in uset:
            seen[r["uid"]][r["coder"]] = 1 if code in r["codes"] else 0
    return OrderedDict((u, [seen[u].get(c) for c in coders]) for u in units if u in seen)


def agreement(rows, codes, coders, units, cross_pairs, consensus_n, base_n):
    out = []
    for code in codes:
        m = binary_matrix(rows, code, coders, units)
        cols = {c: [vals[i] for vals in m.values()] for i, c in enumerate(coders)}
        row = OrderedDict([("code", code), ("alpha", krippendorff_binary(m))])
        kappas = OrderedDict()
        for a, b in combinations(coders, 2):
            k = cohen_kappa(cols[a], cols[b])
            kappas[(a, b)] = k
            row["kappa_%s%s" % (a, b)] = k
            for kk, v in pair_table(cols[a], cols[b]).items():
                row["%s_%s%s" % (kk, a, b)] = v
        applied = [sum(1 for v in vals if v == 1) for vals in m.values()]
        full = [vals for vals in m.values() if all(v is not None for v in vals)]
        ks = [v for v in kappas.values() if not nan(v)]
        xk = [kappas.get(p, kappas.get(p[::-1])) for p in cross_pairs]
        xk = [v for v in xk if not nan(v)]
        n_cons = sum(1 for a in applied if a >= consensus_n)
        row.update([
            ("kappa_mean", sum(ks) / len(ks) if ks else float("nan")),
            ("kappa_cross_family_mean", sum(xk) / len(xk) if xk else float("nan")),
            ("three_rater_agreement", sum(1 for v in full if len(set(v)) == 1) / len(full) if full else float("nan")),
            ("n_any", sum(1 for a in applied if a >= 1)), ("n_consensus", n_cons),
            ("n_unanimous", sum(1 for a in applied if a == len(coders))),
            ("prevalence_consensus_pct", pct(n_cons, base_n)),
        ])
        for c in coders:
            row["n_coder_%s" % c] = sum(1 for v in cols[c] if v == 1)
        out.append(row)
    return out


def load_coded(folder: Path, corpus):
    """Read coder<k>_batch<n>.jsonl files; return (rows, coders, problems)."""
    rows, problems = [], []
    for path in sorted(Path(folder).glob("coder*_batch*.jsonl")):
        coder = path.stem.split("_batch")[0].replace("coder", "")
        batch = path.stem.split("_batch")[1]
        for ln, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            line = line.strip().strip(",")
            if not line or line.startswith("```"):
                continue
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                problems.append("%s line %d: unparseable" % (path.name, ln))
                continue
            uid = str(o.get("uid", ""))
            if uid not in corpus:
                problems.append("%s: unknown uid %r" % (path.name, uid))
                continue
            rows.append(OrderedDict([("coder", coder), ("uid", uid), ("batch", batch),
                                     ("codes", list(dict.fromkeys(o.get("codes") or []))), ("why", o.get("why", "")),
                                     ("uncovered_note", o.get("uncovered_note", ""))]))
    dedup = OrderedDict()
    for r in rows:
        if (r["coder"], r["uid"]) in dedup:
            problems.append("coder %s: duplicate row for %s (last kept)" % (r["coder"], r["uid"]))
        dedup[(r["coder"], r["uid"])] = r
    rows = list(dedup.values())
    return rows, sorted({r["coder"] for r in rows}), problems


def write_csv(path: Path, rows, cols=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = list(rows)
    cols = cols or (list(rows[0].keys()) if rows else ["empty"])
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if nan(v) and not isinstance(v, (str, int)) else v) for k, v in r.items()})


def fmt(x, nd=2):
    return "n/a" if nan(x) else "%.*f" % (nd, x)


def run(*, rows, coders, problems, corpus, book, cfg, rel_units, out: Path, label: str,
        uncertain_pairs=None, spot_decisions=None, low_alpha_decisions=None):
    """Consensus and reliability for one condition. `rel_units` are the units on which reliability
    (and so the drop rule) is computed; consensus and prevalence cover every unit in `corpus`.
    `uncertain_pairs`: (uid, code) consensus pairs held back from prevalence until the researchers'
    spot-check; `spot_decisions`: {(uid, code): True|False} from that spot-check."""
    t = cfg.t
    issue_ids = list(cfg.issue_codes)
    subst = [c["id"] for c in book["codes"]]
    valid = set(subst) | set(issue_ids) | {UNCOVERED}
    bad = sorted({c for r in rows for c in r["codes"] if c not in valid})
    for r in rows:
        r["codes"] = [c for c in r["codes"] if c in valid]
    seen = defaultdict(set)
    for r in rows:
        seen[r["coder"]].add(r["uid"])
    missing = OrderedDict((c, sorted(set(corpus) - seen[c])) for c in coders)
    k_cons = int(t["consensus"])

    tally = defaultdict(set)
    for r in rows:
        for c in r["codes"]:
            tally[(r["uid"], c)].add(r["coder"])
    cons = [OrderedDict([("uid", u), ("code", c), ("n_coders", len(cs)), ("coders", "".join(sorted(cs))),
                         ("unanimous", len(cs) == len(coders))])
            for (u, c), cs in sorted(tally.items()) if len(cs) >= k_cons]
    issue_by_unit = defaultdict(set)
    for r in rows:
        if any(c in issue_ids for c in r["codes"]):
            issue_by_unit[r["uid"]].add(r["coder"])
    issue_units = sorted(u for u, cs in issue_by_unit.items() if len(cs) >= k_cons)
    base = [u for u in corpus if u not in issue_units]
    rel_units_l = [u for u in corpus if u in set(rel_units)]
    rel_base = [u for u in rel_units_l if u not in issue_units]
    rel = agreement(rows, subst + issue_ids + [UNCOVERED], coders, rel_units_l, cfg.cross_family_pairs,
                    k_cons, len(rel_base))
    relm = {r["code"]: r for r in rel}

    # drop rule
    floor = float(t["alpha_drop"])
    dropped = [c for c in subst if not nan(relm[c]["alpha"]) and relm[c]["alpha"] < floor]
    undefined = [c for c in subst if nan(relm[c]["alpha"])]
    retained = [c for c in subst if c not in dropped and c not in undefined]
    uncertain = set(uncertain_pairs or [])
    spot = spot_decisions or {}

    by_code, pending = defaultdict(set), defaultdict(set)
    for r in cons:
        u, c = r["uid"], r["code"]
        if c not in subst or u in issue_units:
            continue
        if (u, c) in uncertain and spot.get((u, c)) is not True:
            if spot.get((u, c)) is None:
                pending[c].add(u)
            continue
        by_code[c].add(u)
    books = {c["id"]: c for c in book["codes"]}
    prevalence = []
    for cid in subst:
        c = books[cid]
        prevalence.append(OrderedDict([
            ("code", cid), ("rq", c.get("rq", "")), ("label", c["label"]),
            ("status", "retained" if cid in retained else "dropped: alpha below %.2f" % floor if cid in dropped else "dropped: alpha undefined"),
            ("n_units", len(by_code[cid])), ("pct_units", pct(len(by_code[cid]), len(base))),
            ("n_pending_spot_check", len(pending[cid])),
            ("n_any_coder", sum(1 for (u, k) in tally if k == cid)), ("alpha", relm[cid]["alpha"]),
            ("kappa_cross_family_mean", relm[cid]["kappa_cross_family_mean"]),
            ("n_analysts_at_discovery", c.get("n_analysts", 0)), ("n_units_at_discovery", c.get("n_units", 0)),
        ]))
    prevalence.sort(key=lambda p: (p["status"] != "retained", -p["n_units"], p["code"]))

    n_any = len(tally)
    n_cons_pairs = sum(1 for cs in tally.values() if len(cs) >= k_cons)
    subst_pairs = {k: v for k, v in tally.items() if k[1] in subst}
    unc_by_unit = defaultdict(list)
    for r in rows:
        if UNCOVERED in r["codes"]:
            unc_by_unit[r["uid"]].append(OrderedDict([("coder", r["coder"]), ("note", r["uncovered_note"] or r["why"])]))
    alphas = [relm[c]["alpha"] for c in subst if not nan(relm[c]["alpha"])]
    xk = [relm[c]["kappa_cross_family_mean"] for c in subst if not nan(relm[c]["kappa_cross_family_mean"])]
    per_coder = OrderedDict()
    for c in coders:
        mine = [r for r in rows if r["coder"] == c]
        n_sub = sum(len([x for x in r["codes"] if x in subst]) for r in mine)
        per_coder[c] = OrderedDict([
            ("family", cfg.coders.get(c, "?")), ("n_units", len(mine)), ("n_assignments", n_sub),
            ("codes_per_unit", round(n_sub / len(mine), 2) if mine else 0),
            ("n_issue", sum(1 for r in mine if any(x in issue_ids for x in r["codes"]))),
            ("n_uncovered", sum(1 for r in mine if UNCOVERED in r["codes"])),
            ("n_no_code", sum(1 for r in mine if not r["codes"])),
        ])
    summary = OrderedDict([
        ("condition", label), ("coders", coders), ("coder_families", OrderedDict((c, cfg.coders.get(c)) for c in coders)),
        ("cross_family_pairs", ["%s-%s" % p for p in cfg.cross_family_pairs]),
        ("consensus_rule", "%d of %d coders" % (k_cons, len(coders))),
        ("n_units", len(corpus)), ("n_reliability_units", len(rel_units_l)), ("reliability_units", cfg.d["reliability"]["units"]),
        ("n_codes", len(subst)), ("codebook_version", book.get("version")),
        ("n_issue_units_consensus", len(issue_units)), ("issue_units", issue_units), ("prevalence_base", len(base)),
        ("alpha_median", median(alphas)), ("alpha_min", min(alphas) if alphas else None), ("alpha_max", max(alphas) if alphas else None),
        ("n_codes_alpha_below_%s" % t["alpha_drop"], len(dropped)),
        ("n_codes_alpha_at_or_above_%s" % t["alpha_high"], sum(1 for a in alphas if a >= float(t["alpha_high"]))),
        ("n_codes_alpha_undefined", len(undefined)),
        ("codes_dropped_alpha_below_floor", dropped), ("codes_alpha_undefined", undefined), ("codes_retained", retained),
        ("cross_family_kappa_median", median(xk)),
        ("survival", OrderedDict([
            ("n_unit_code_pairs_any_coder", n_any), ("n_unit_code_pairs_consensus", n_cons_pairs),
            ("rate_pairs", round(n_cons_pairs / n_any, 3) if n_any else None),
            ("rate_pairs_substantive_codes_only",
             round(sum(1 for cs in subst_pairs.values() if len(cs) >= k_cons) / len(subst_pairs), 3) if subst_pairs else None)])),
        ("n_uncovered_any_coder", len(unc_by_unit)),
        ("n_uncovered_consensus", sum(1 for v in unc_by_unit.values() if len(v) >= k_cons)),
        ("uncovered_units", OrderedDict((u, unc_by_unit[u]) for u in sorted(unc_by_unit))),
        ("n_pairs_pending_spot_check", sum(len(v) for v in pending.values())),
        ("low_alpha_decisions", OrderedDict((c, (low_alpha_decisions or {}).get(c, {}).get("decision", "pending: the researchers decide (refine and recode, or drop)"))
                                            for c in dropped)),
        ("per_coder", per_coder),
        ("integrity", OrderedDict([("invalid_codes_used_and_dropped", bad),
                                   ("units_missing_per_coder", OrderedDict((c, len(v)) for c, v in missing.items())),
                                   ("problems", problems)])),
    ])
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "reliability.csv", rel)
    write_csv(out / "consensus.csv", cons)
    write_csv(out / "consensus_retained.csv", [r for r in cons if r["code"] in retained and r["uid"] not in issue_units
                                               and ((r["uid"], r["code"]) not in uncertain or spot.get((r["uid"], r["code"])) is True)])
    write_csv(out / "prevalence.csv", prevalence)
    write_csv(out / "coder_long.csv", [OrderedDict([("coder", r["coder"]), ("uid", r["uid"]), ("codes", "|".join(r["codes"])),
                                                    ("why", r["why"]), ("uncovered_note", r["uncovered_note"])]) for r in rows])
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    (out / "reliability_report.md").write_text(report_md(summary, rel, book, cfg, low_alpha_decisions or {}), encoding="utf-8")
    print("consensus %s: %d coders x %d units; alpha median %s (min %s, max %s); %d codes dropped below %.2f, %d undefined; "
          "cross-family kappa median %s; survival %s; issue units %d; uncovered %d"
          % (label, len(coders), len(corpus), fmt(summary["alpha_median"]), fmt(summary["alpha_min"]), fmt(summary["alpha_max"]),
             len(dropped), floor, len(undefined), fmt(summary["cross_family_kappa_median"]), summary["survival"]["rate_pairs"],
             len(issue_units), len(unc_by_unit)))
    if bad:
        print("   ! invalid codes used and dropped: %s" % bad)
    for c, v in missing.items():
        if v:
            print("   ! coder %s did not code %d units" % (c, len(v)))
    return OrderedDict([("summary", summary), ("rows", rows), ("cons", cons), ("rel", rel)])


def report_md(s, rel, book, cfg, decisions=None) -> str:
    """The reliability appendix for one condition: distribution, every code, dropped codes."""
    t = cfg.t
    books = {c["id"]: c for c in book["codes"]}
    relm = {r["code"]: r for r in rel}
    coders = s["coders"]
    pairs = list(combinations(coders, 2))
    L = ["# Reliability: condition %s" % s["condition"], ""]
    if not pairs:
        return "\n".join(L + ["Fewer than two coders produced output; no agreement can be computed."]) + "\n"
    L.append("Reliability units: %s (%d units). Consensus rule: %s. Codebook version %s." % (
        s["reliability_units"], s["n_reliability_units"], s["consensus_rule"], s["codebook_version"]))
    L.append("")
    L.append("| | |\n|---|---|")
    L.append("| Codes | %d |" % s["n_codes"])
    L.append("| Alpha median / min / max | %s / %s / %s |" % (fmt(s["alpha_median"]), fmt(s["alpha_min"]), fmt(s["alpha_max"])))
    L.append("| Codes with alpha below %s (dropped) | %d |" % (t["alpha_drop"], len(s["codes_dropped_alpha_below_floor"])))
    L.append("| Codes with alpha at or above %s | %d |" % (t["alpha_high"], s["n_codes_alpha_at_or_above_%s" % t["alpha_high"]]))
    L.append("| Codes with alpha undefined (no variation; not reported) | %d |" % s["n_codes_alpha_undefined"])
    L.append("| Cross-family kappa median (pairs %s) | %s |" % (", ".join(s["cross_family_pairs"]) or "none", fmt(s["cross_family_kappa_median"])))
    sv = s["survival"]
    L.append("| Survival (pairs at consensus / proposed) | %s / %s = %s |" % (sv["n_unit_code_pairs_consensus"], sv["n_unit_code_pairs_any_coder"], sv["rate_pairs"]))
    L.append("| Issue units at consensus (excluded from prevalence) | %d |" % s["n_issue_units_consensus"])
    L.append("| Uncovered: any coder / consensus | %d / %d |" % (s["n_uncovered_any_coder"], s["n_uncovered_consensus"]))
    L.append("")
    L.append("No interval is placed on the median.%s" % (
        "" if len(set(s["coder_families"].values())) == len(coders) else
        " Two coders share a family; the cross-family kappa is the agreement that does not rest on one family."))
    L.append("")
    L.append("## Every code")
    L.append("")
    head = "| Code | RQ | Status | alpha | " + " | ".join("kappa %s%s" % p for p in pairs) + " | " + \
           " | ".join("2x2 %s%s (a/b/c/d)" % p for p in pairs) + " | PA %s%s | NA %s%s | any | consensus | unanimous |" % (pairs[0] * 2)
    L.append(head)
    L.append("|" + "---|" * (head.count("|") - 1))
    for code in [c["id"] for c in book["codes"]] + list(cfg.issue_codes) + [UNCOVERED]:
        r = relm.get(code)
        if not r:
            continue
        status = ("retained" if code in s["codes_retained"] else "DROPPED" if code in s["codes_dropped_alpha_below_floor"]
                  else "undefined" if code in s["codes_alpha_undefined"] else "issue/uncovered")
        p0 = "%s%s" % pairs[0]
        L.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            code, books.get(code, {}).get("rq", ""), status, fmt(r["alpha"]),
            " | ".join(fmt(r["kappa_%s%s" % p]) for p in pairs),
            " | ".join("%s/%s/%s/%s" % tuple(r["%s_%s%s" % (k, a, b)] for k in "abcd") for a, b in pairs),
            fmt(r["pos_agree_%s" % p0]), fmt(r["neg_agree_%s" % p0]), r["n_any"], r["n_consensus"], r["n_unanimous"]))
    L.append("")
    L.append("## Codes dropped from the results")
    L.append("")
    L.append("Codes with alpha below %s are held out of the results: coders could not apply them consistently, so they "
             "cannot support a finding. The researchers decide, per code, to refine the definition and recode the corpus, or "
             "to drop the code (`human.py low-alpha`). They are listed here with their definitions, agreement counts and that "
             "decision." % t["alpha_drop"])
    L.append("")
    decisions = decisions or {}
    for code in s["codes_dropped_alpha_below_floor"] + s["codes_alpha_undefined"]:
        c, r = books[code], relm[code]
        L.append("### %s %s (%s)" % (code, c["label"], c.get("rq", "")))
        L.append("")
        dd = decisions.get(code)
        if code in s["codes_dropped_alpha_below_floor"]:
            L.append("- Researchers' decision: %s" % (("**%s**%s%s" % (dd["decision"], (": " + dd["reason"]) if dd.get("reason") else "",
                                                                       (" (%s)" % dd["decided_by"]) if dd.get("decided_by") else ""))
                                                       if dd else "pending (refine and recode, or drop)"))
        else:
            L.append("- Alpha undefined (no variation among the coders on the reliability units); not reported.")
        L.append("- alpha %s; assigned by any coder on %d units, at consensus on %d, unanimously on %d" % (
            fmt(r["alpha"]), r["n_any"], r["n_consensus"], r["n_unanimous"]))
        L.append("- Definition: %s" % c.get("definition", ""))
        if c.get("include"):
            L.append("- Include: %s" % c["include"])
        if c.get("exclude"):
            L.append("- Exclude: %s" % c["exclude"])
        L.append("")
    if not (s["codes_dropped_alpha_below_floor"] or s["codes_alpha_undefined"]):
        L.append("None.")
    return "\n".join(L) + "\n"
