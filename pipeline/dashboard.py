#!/usr/bin/env python3
"""
The results dashboard: <workspace>/dashboard.html, one self-contained page (no network, no CDN)
built from the run's artifacts after consensus. `council.py dashboard` writes it; `council.py
consensus` and `council.py report` refresh it.

Sections: the run; what each stage produced (codes per analyst, challenges and answers in Full,
candidate and approved codebook sizes); reliability (median alpha, codes below the floor with their
definitions and the researchers' decision, codes at or above 0.80, cross-family kappa); prevalence
per code; the codebook with definitions and example quotes; the human checks; and calls, tokens and
cost by stage, with model calls and decision-model requests apart.

Standard library only.
"""
from __future__ import annotations

import html
import json
from collections import OrderedDict, defaultdict
from datetime import datetime, timezone

M = None   # the council module (cfg, W, helpers), bound by bind()


def bind(module):
    global M
    M = module


def esc(x) -> str:
    return html.escape("" if x is None else str(x), quote=True)


def num(x, nd=2):
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return None if f != f else round(f, nd)


def fmt(x, nd=2):
    v = num(x, nd)
    return "n/a" if v is None else ("%.*f" % (nd, v))


def tally(path):
    t = OrderedDict([("ACCEPT", 0), ("REJECT", 0), ("PARTIAL", 0)])
    for a in M.rj(path).get("answers", []):
        k = (a.get("answer") or "").upper()
        t[k if k in t else "PARTIAL"] += 1
    return t


# --------------------------------------------------------------------------- data
def collect() -> dict:
    cfg, W, rj = M.cfg, M.W, M.rj
    corpus = M.load_corpus()
    sp = M.splits()
    prim = M.primary_condition()
    conds = [c for c in M.CONDITIONS if (W / "results" / c / "summary.json").exists()]
    if prim not in conds and conds:
        prim = conds[-1]
    summ = rj(W / "results" / prim / "summary.json")
    rel = {r["code"]: r for r in M.read_csv(W / "results" / prim / "reliability.csv")} if (W / "results" / prim / "reliability.csv").exists() else {}
    prev = {r["code"]: r for r in M.read_csv(W / "results" / prim / "prevalence.csv")} if (W / "results" / prim / "prevalence.csv").exists() else {}
    ap = rj(W / "codebooks" / "approved_codebook.json")
    dec = M.low_alpha_decisions()

    analysts = []
    for A, fam in cfg.analysts.items():
        s0 = rj(W / "discovery" / "validation" / ("v0_analyst_%s.json" % A)).get("stats", {})
        s1 = rj(W / "discovery" / "validation" / ("v1_analyst_%s.json" % A)).get("stats", {})
        ch = rj(W / "discovery" / "challenges" / ("adversary_%s.json" % A))
        analysts.append(OrderedDict([("id", A), ("family", fam), ("v0", s0.get("n_codes")), ("v0_layers", s0.get("n_by_layer") or {}),
                                     ("v1", s1.get("n_codes") if cfg.full else None), ("challenges", len(ch.get("challenges", []))),
                                     ("quarantined", len(ch.get("quarantined_codes") or [])),
                                     ("answers", tally(W / "discovery" / "answers" / ("answer_%s.json" % A))),
                                     ("adversary", cfg.analyst_adversary.get(A))]))
    recon = OrderedDict()
    for cond in (["lite", "full"] if cfg.full else ["lite"]):
        b = rj(W / "codebooks" / ("candidate_%s.json" % cond))
        if b:
            recon[cond] = OrderedDict([("raw", b.get("n_raw_codes")), ("groups", b.get("n_groups")), ("kept", b.get("n_kept")),
                                       ("dropped_floor", b.get("n_dropped_below_floor")), ("quarantined", b.get("n_quarantined", 0)),
                                       ("dropped", [d["label"] for d in b.get("dropped", [])])])
    recon_ch = rj(W / "reconciliation" / "full" / "adversary_challenges.json").get("challenges", []) if cfg.full else []
    recon_ans = tally(W / "reconciliation" / "full" / "reconciler_answers.json") if cfg.full else None
    coders = []
    cdir = W / "coding" / M.adversary_cond() / "challenges"
    diff = rj(W / "results" / "v0_v1_diff.json")
    for k, fam in cfg.coders.items():
        n, t = 0, OrderedDict([("ACCEPT", 0), ("REJECT", 0), ("PARTIAL", 0)])
        for p in (sorted(cdir.glob("coder%s_batch*.json" % k)) if cdir.exists() else []):
            n += len(M.read_json(p).get("challenges", []))
            for kk, v in tally(cdir.parent / "answers" / p.name).items():
                t[kk] += v
        pc = (diff.get("per_coder") or {}).get(k, {})
        coders.append(OrderedDict([("id", k), ("family", fam), ("adversary", cfg.coder_adversary.get(k)), ("challenges", n), ("answers", t),
                                   ("added", pc.get("n_added", 0)), ("removed", pc.get("n_removed", 0))]))
    conds_s = OrderedDict((c, rj(W / "results" / c / "summary.json")) for c in conds)

    # cost by stage, model calls and decision-model requests apart
    calls, estimated = defaultdict(lambda: OrderedDict([("calls", 0), ("input", 0), ("output", 0), ("cost", 0.0), ("priced", True)])), set()
    prices = cfg.d.get("prices") or {}
    log = W / "logs" / "calls.jsonl"
    stage_order = []
    if log.exists():
        for line in log.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("status") != "ok":
                continue
            kind = "dm" if r.get("role_family") == "decision-model" else "llm"
            key = (kind, r["stage"])
            if key not in stage_order:
                stage_order.append(key)
            a = calls[key]
            i, o = r.get("input_tokens") or 0, r.get("output_tokens") or 0
            a["calls"] += 1
            a["input"] += i
            a["output"] += o
            pr = prices.get(r.get("model_id"))
            if pr:
                a["cost"] += (i * float(pr[0]) + o * float(pr[1])) / 1e6
            elif r.get("cost_usd_reported"):
                a["cost"] += float(r["cost_usd_reported"])
            else:
                a["priced"] = False
            if r.get("tokens_estimated"):
                estimated.add(kind)
    import report as RP
    stage_order.sort(key=lambda ks: RP.stage_rank(ks[1]))
    cost = OrderedDict([("llm", [(s, calls[(k, s)]) for k, s in stage_order if k == "llm"]),
                        ("dm", [(s, calls[(k, s)]) for k, s in stage_order if k == "dm"]), ("estimated", sorted(estimated))])

    spot = W / "human" / "05_spot_check" / "decisions.csv"
    spot_rows = M.read_csv(spot) if spot.exists() else None
    return OrderedDict([
        ("cfg", cfg), ("corpus", corpus), ("splits", sp), ("prim", prim), ("conds", conds_s), ("summ", summ), ("rel", rel),
        ("prev", prev), ("approved", ap), ("decisions", dec), ("analysts", analysts), ("recon", recon), ("recon_ch", recon_ch),
        ("recon_ans", recon_ans), ("coders", coders), ("cost", cost), ("heldout", rj(W / "results" / "human_council_agreement.json")),
        ("spot", spot_rows), ("man", rj(W / "manifest.json"))])


# --------------------------------------------------------------------------- page
CSS = """
:root { color-scheme: light;
  --bg: #f5f5f3; --surface: #fcfcfb; --ink: #0b0b0b; --ink-2: #52514e; --ink-3: #6f6e69; --line: #e2e1dc; --grid: #ecebe6;
  --series: #2a78d6; --series-soft: #dce9f8; --critical: #d03b3b; --good: #0ca30c; --warning: #fab219; --ref: #8a8984; }
@media (prefers-color-scheme: dark) { :root:where(:not([data-theme="light"])) { color-scheme: dark;
  --bg: #121211; --surface: #1a1a19; --ink: #ffffff; --ink-2: #c3c2b7; --ink-3: #9d9c93; --line: #2f2f2c; --grid: #262624;
  --series: #3987e5; --series-soft: #1f3550; --ref: #8f8e86; } }
:root[data-theme="dark"] { color-scheme: dark;
  --bg: #121211; --surface: #1a1a19; --ink: #ffffff; --ink-2: #c3c2b7; --ink-3: #9d9c93; --line: #2f2f2c; --grid: #262624;
  --series: #3987e5; --series-soft: #1f3550; --ref: #8f8e86; }
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink); font: 15px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
.wrap { max-width: 1120px; margin: 0 auto; padding: 24px 16px 64px; }
header h1 { font-size: 26px; line-height: 1.2; margin: 0 0 4px; }
.sub { color: var(--ink-2); margin: 0; }
nav.toc { display: flex; flex-wrap: wrap; gap: 6px 14px; margin: 16px 0 8px; font-size: 14px; }
a { color: var(--series); }
section { background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 18px 18px 20px; margin-top: 18px; }
h2 { font-size: 19px; margin: 0 0 12px; }
h3 { font-size: 15px; margin: 18px 0 8px; color: var(--ink-2); }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 10px; }
.tile { border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px; }
.tile .v { font-size: 24px; overflow-wrap: anywhere; font-weight: 600; font-variant-numeric: tabular-nums; line-height: 1.2; }
.tile .k { color: var(--ink-2); font-size: 13px; }
.scroll { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: 14px; font-variant-numeric: tabular-nums; }
th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--line); vertical-align: top; }
th { color: var(--ink-2); font-weight: 600; }
td.n, th.n { text-align: right; }
.chart { margin: 8px 0 4px; }
.row { display: grid; grid-template-columns: minmax(120px, 34%) 1fr; gap: 10px; align-items: center; padding: 3px 0; }
.row .lab { font-size: 13px; color: var(--ink); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.row .lab b { font-weight: 600; margin-right: 6px; }
.track { position: relative; height: 22px; }
.plot { position: absolute; left: 0; right: 52px; top: 0; bottom: 0; }
.bar { position: absolute; left: 0; top: 4px; height: 14px; background: var(--series); border-radius: 0 4px 4px 0; min-width: 2px; }
.bar.low { background: var(--critical); }
.bar:hover, .bar:focus { outline: 2px solid var(--ink); outline-offset: 1px; }
.val { position: absolute; top: 2px; font-size: 12px; color: var(--ink-2); white-space: nowrap; padding-left: 6px; }
.refline { position: absolute; top: -2px; bottom: -2px; border-left: 1px dashed var(--ref); }
.axis { position: relative; height: 18px; margin-left: calc(34% + 10px); margin-right: 52px; font-size: 11px; color: var(--ink-3); }
.axis span { position: absolute; transform: translateX(-50%); }
.legend { display: flex; flex-wrap: wrap; gap: 14px; font-size: 13px; color: var(--ink-2); margin-top: 6px; }
.sw { display: inline-block; width: 12px; height: 12px; border-radius: 3px; vertical-align: -2px; margin-right: 5px; }
.sw.dash { width: 0; height: 14px; border-left: 1px dashed var(--ref); border-radius: 0; margin-right: 8px; }
.status { display: inline-flex; align-items: center; gap: 4px; font-size: 13px; white-space: nowrap; }
.status .ic { font-weight: 700; }
.status.ok .ic { color: var(--good); } .status.low .ic { color: var(--critical); } .status.pend .ic { color: var(--warning); }
.code { border-top: 1px solid var(--line); padding: 12px 0; }
.code:first-of-type { border-top: 0; }
.code h3 { margin: 0 0 4px; color: var(--ink); font-size: 16px; }
.meta { display: flex; flex-wrap: wrap; gap: 4px 14px; color: var(--ink-2); font-size: 13px; margin-bottom: 6px; }
dl { margin: 0; display: grid; grid-template-columns: max-content 1fr; gap: 2px 12px; font-size: 14px; }
dt { color: var(--ink-2); }
dd { margin: 0; }
blockquote { margin: 6px 0; padding: 4px 10px; border-left: 3px solid var(--series-soft); color: var(--ink); font-size: 14px; }
blockquote .uid { color: var(--ink-3); font-size: 12px; margin-left: 6px; }
.note { color: var(--ink-2); font-size: 13px; margin: 8px 0 0; }
.decision { border: 1px solid var(--line); border-left: 4px solid var(--critical); border-radius: 6px; padding: 10px 12px; margin: 8px 0; }
.empty { color: var(--ink-2); }
details summary { cursor: pointer; color: var(--ink-2); font-size: 14px; margin-top: 8px; }
.theme { float: right; font-size: 13px; }
.theme button { font: inherit; background: none; border: 1px solid var(--line); color: var(--ink-2); border-radius: 6px; padding: 2px 8px; cursor: pointer; }
@media (max-width: 640px) { .row { grid-template-columns: 1fr; gap: 2px; } .axis { margin-left: 0; } header h1 { font-size: 22px; } }
"""

JS = """
(function(){
  var b=document.getElementById('theme');
  if(!b) return;
  b.addEventListener('click',function(){
    var r=document.documentElement, cur=r.getAttribute('data-theme');
    var dark = cur ? cur==='dark' : window.matchMedia('(prefers-color-scheme: dark)').matches;
    r.setAttribute('data-theme', dark ? 'light' : 'dark');
  });
})();
"""


def status_badge(code, summ, decisions):
    if code in (summ.get("codes_dropped_alpha_below_floor") or []):
        d = (decisions.get(code) or {}).get("decision")
        if d == "drop":
            return '<span class="status low"><span class="ic" aria-hidden="true">&#x2715;</span>below 0.67, dropped by the researchers</span>'
        if d == "refine":
            return '<span class="status pend"><span class="ic" aria-hidden="true">&#x21bb;</span>below 0.67, refine and recode</span>'
        return '<span class="status pend"><span class="ic" aria-hidden="true">?</span>below 0.67, awaiting the researchers</span>'
    if code in (summ.get("codes_alpha_undefined") or []):
        return '<span class="status pend"><span class="ic" aria-hidden="true">&ndash;</span>alpha undefined</span>'
    return '<span class="status ok"><span class="ic" aria-hidden="true">&#x2713;</span>retained</span>'


def bar_chart(rows, vmax, refs=(), fmt_v=lambda v: fmt(v), low=lambda r: False, label=""):
    """rows: [(id, label, value, tooltip)]; a horizontal single-series bar chart in HTML."""
    out = ['<div class="chart" role="img" aria-label="%s">' % esc(label)]
    for cid, lab, v, tip in rows:
        w = 0 if v is None or vmax <= 0 else max(0.0, min(1.0, v / vmax)) * 100
        out.append('<div class="row"><div class="lab" title="%s"><b>%s</b>%s</div><div class="track">' % (esc(lab), esc(cid), esc(lab)))
        out.append('<div class="plot">')
        for r in refs:
            out.append('<div class="refline" style="left:%.2f%%" aria-hidden="true"></div>' % (100 * r / vmax))
        if v is not None:
            out.append('<div class="bar%s" style="width:%.2f%%" tabindex="0" title="%s"></div>' % (" low" if low(cid) else "", w, esc(tip)))
            out.append('<div class="val" style="left:%.2f%%">%s</div>' % (w, esc(fmt_v(v))))
        else:
            out.append('<div class="val" style="left:0">n/a</div>')
        out.append('</div></div></div>')
    out.append('</div>')
    return "".join(out)


def axis(vmax, ticks):
    return '<div class="axis" aria-hidden="true">%s</div>' % "".join('<span style="left:%.2f%%">%s</span>' % (100 * t / vmax, t) for t in ticks)


def build() -> str:
    d = collect()
    cfg, W, summ, rel, prev, ap, dec = d["cfg"], M.W, d["summ"], d["rel"], d["prev"], d["approved"], d["decisions"]
    t = cfg.t
    floor, high = float(t["alpha_drop"]), float(t["alpha_high"])
    codes = ap.get("codes", [])
    labels = {c["id"]: c["label"] for c in codes}
    P = []
    a = P.append
    a('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">')
    a('<title>Council Results</title><style>%s</style></head><body><div class="wrap">' % CSS)
    a('<header><div class="theme"><button type="button" id="theme" aria-label="Switch light or dark theme">Light / dark</button></div>')
    a('<h1>Council results: %s</h1>' % esc(W.name))
    a('<p class="sub">Mode <b>%s</b> &middot; %d %s &middot; %d research question%s &middot; codebook version %s &middot; results of condition <b>%s</b> &middot; generated %s</p>' % (
        esc(cfg.mode.capitalize()), len(d["corpus"]), esc(cfg.study["unit_name_plural"]), len(cfg.rqs), "" if len(cfg.rqs) == 1 else "s",
        esc(ap.get("version", "n/a")), esc(d["prim"]), datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")))
    links = [("RESULTS.md", "RESULTS.md (the full report)"), ("results/%s/reliability_report.md" % d["prim"], "Reliability report"),
             ("human/02_author_review/codebook_review.html", "Author review dashboard")]
    a('<p class="sub">%s</p>' % " &middot; ".join('<a href="%s">%s</a>' % (esc(h), esc(l)) for h, l in links if (W / h).exists()))
    a('<nav class="toc" aria-label="Sections"><a href="#stages">Stages</a><a href="#reliability">Reliability</a><a href="#prevalence">Prevalence</a>'
      '<a href="#codebook">Codebook</a><a href="#human">Human checks</a><a href="#cost">Calls and cost</a></nav></header>')
    if "demo" in (cfg.d.get("data_governance") or "").lower():
        a('<section><p class="note" style="margin:0"><b>Demo.</b> %s</p></section>' % esc(cfg.d.get("data_governance")))

    # tiles
    alphas = summ.get("alpha_median")
    a('<section aria-labelledby="h-over"><h2 id="h-over">At a glance</h2><div class="tiles">')
    tiles = [(len(d["corpus"]), cfg.study["unit_name_plural"]),
             (d["recon"].get(cfg.mode, {}).get("raw", "n/a"), "raw codes from the analysts"),
             (d["recon"].get(cfg.mode, {}).get("kept", "n/a"), "candidate codes"),
             (ap.get("n_approved", "n/a"), "approved codes"),
             (len(summ.get("codes_retained") or []), "codes retained after reliability"),
             (fmt(alphas), "median Krippendorff's alpha")]
    for v, k in tiles:
        a('<div class="tile"><div class="v">%s</div><div class="k">%s</div></div>' % (esc(v), esc(k)))
    a('</div></section>')

    # stages
    a('<section id="stages" aria-labelledby="h-st"><h2 id="h-st">What each stage produced</h2>')
    a('<h3>Stage 1: discovery, codes per analyst</h3><div class="scroll"><table><thead><tr><th>Analyst</th><th>Family</th>'
      '<th class="n">Codes v0</th><th class="n">semantic / latent / contrastive</th>%s</tr></thead><tbody>' % (
          '<th class="n">Codes v1</th><th>Adversary</th><th class="n">Challenges</th><th class="n">Accept / reject / partial</th><th class="n">Quarantined</th>' if cfg.full else ""))
    for x in d["analysts"]:
        lay = " / ".join(str((x["v0_layers"] or {}).get(l, 0)) for l in M.LAYERS)
        a('<tr><td>%s</td><td>%s</td><td class="n">%s</td><td class="n">%s</td>' % (esc(x["id"]), esc(x["family"]), esc(x["v0"]), lay))
        if cfg.full:
            an = x["answers"]
            a('<td class="n">%s</td><td>%s</td><td class="n">%d</td><td class="n">%d / %d / %d</td><td class="n">%d</td>' % (
                esc(x["v1"]), esc(x["adversary"]), x["challenges"], an["ACCEPT"], an["REJECT"], an["PARTIAL"], x["quarantined"]))
        a('</tr>')
    a('</tbody></table></div>')
    a('<h3>Stage 2: reconciliation, candidate codebook</h3><div class="scroll"><table><thead><tr><th>Condition</th><th class="n">Raw codes</th>'
      '<th class="n">Groups</th><th class="n">Kept at the %s-unit floor</th><th class="n">Below the floor</th><th class="n">Quarantined</th></tr></thead><tbody>' % t["support_floor"])
    for cond, r in d["recon"].items():
        a('<tr><td>%s</td><td class="n">%s</td><td class="n">%s</td><td class="n">%s</td><td class="n">%s</td><td class="n">%s</td></tr>' % (
            esc(cond.capitalize()), r["raw"], r["groups"], r["kept"], r["dropped_floor"], r["quarantined"]))
    a('</tbody></table></div>')
    if cfg.full and d["recon_ch"]:
        ra = d["recon_ans"]
        a('<p class="note">Reconciliation adversary (%s): %d challenges; the reconciler accepted %d, rejected %d, partly accepted %d.</p>' % (
            esc(cfg.recon_adversary), len(d["recon_ch"]), ra["ACCEPT"], ra["REJECT"], ra["PARTIAL"]))
    rv = ap.get("review") or {}
    if ap:
        a('<h3>Stage 3: author review</h3><p>Reviewed by %s. %d edits (%s). <b>%d candidate codes became %d approved codes</b>; %d quarantined candidate(s) admitted. Blind-pass codes the council lacked: %s.</p>' % (
            esc(rv.get("reviewed_by") or "not recorded"), rv.get("n_edits", 0),
            esc(", ".join("%s %d" % kv for kv in (rv.get("edits_by_type") or {}).items()) or "none"),
            d["recon"].get(cfg.mode, {}).get("kept", 0) or 0, ap.get("n_approved", 0), ap.get("n_quarantined_accepted", 0),
            esc("; ".join(rv.get("blind_pass_codes_missing") or []) or "none recorded")))
    if cfg.full and d["coders"]:
        a('<h3>Stage 4: coding adversaries</h3><div class="scroll"><table><thead><tr><th>Coder</th><th>Family</th><th>Adversary</th>'
          '<th class="n">Challenges</th><th class="n">Accept / reject / partial</th><th class="n">Cells added / removed</th></tr></thead><tbody>')
        for x in d["coders"]:
            an = x["answers"]
            a('<tr><td>%s</td><td>%s</td><td>%s</td><td class="n">%d</td><td class="n">%d / %d / %d</td><td class="n">+%d / &minus;%d</td></tr>' % (
                esc(x["id"]), esc(x["family"]), esc(x["adversary"]), x["challenges"], an["ACCEPT"], an["REJECT"], an["PARTIAL"], x["added"], x["removed"]))
        a('</tbody></table></div>')
    a('</section>')

    # reliability
    a('<section id="reliability" aria-labelledby="h-rel"><h2 id="h-rel">Reliability (condition %s)</h2>' % esc(d["prim"]))
    if not summ:
        a('<p class="empty">No coding results yet: run Stage 4.</p></section>')
    else:
        low = summ.get("codes_dropped_alpha_below_floor") or []
        hi = [c for c in summ.get("codes_retained", []) if (num(rel.get(c, {}).get("alpha")) or 0) >= high]
        a('<div class="tiles">')
        for v, k in [(fmt(summ.get("alpha_median")), "median alpha"), ("%s to %s" % (fmt(summ.get("alpha_min")), fmt(summ.get("alpha_max"))), "min to max"),
                     (len(low), "codes below %s" % floor), (len(hi), "codes at or above %s" % high),
                     (fmt(summ.get("cross_family_kappa_median")), "cross-family kappa (median)"),
                     ("%s (%d)" % (summ.get("reliability_units"), summ.get("n_reliability_units", 0)), "reliability units")]:
            a('<div class="tile"><div class="v">%s</div><div class="k">%s</div></div>' % (esc(v), esc(k)))
        a('</div><h3>Krippendorff\'s alpha per code</h3>')
        rows = []
        for c in codes:
            v = num(rel.get(c["id"], {}).get("alpha"), 3)
            rows.append((c["id"], c["label"], v, "%s %s: alpha %s" % (c["id"], c["label"], fmt(v))))
        a(bar_chart(rows, 1.0, refs=(floor, high), low=lambda cid: cid in low, label="Krippendorff's alpha per code; reference lines at %s and %s" % (floor, high)))
        a(axis(1.0, [0, 0.25, 0.5, 0.75, 1.0]))
        a('<div class="legend"><span><span class="sw" style="background:var(--series)"></span>alpha of a retained code</span>'
          '<span><span class="sw" style="background:var(--critical)"></span>below %s (goes to the researchers)</span>'
          '<span><span class="sw dash"></span>%s floor and %s high mark</span></div>' % (floor, floor, high))
        a('<h3>Codes below %s and the researchers\' decision</h3>' % floor)
        if not low:
            a('<p class="empty">None.</p>')
        for cid in low:
            c = next((x for x in codes if x["id"] == cid), {})
            r = rel.get(cid, {})
            dd = dec.get(cid)
            a('<div class="decision"><b>%s %s</b> (%s) &middot; alpha %s &middot; any coder %s, consensus %s, unanimous %s<br>' % (
                esc(cid), esc(c.get("label")), esc(c.get("rq")), fmt(r.get("alpha")), esc(r.get("n_any")), esc(r.get("n_consensus")), esc(r.get("n_unanimous"))))
            a('<dl><dt>Definition</dt><dd>%s</dd>%s%s<dt>Decision</dt><dd>%s</dd></dl></div>' % (
                esc(c.get("definition")), ("<dt>Include</dt><dd>%s</dd>" % esc(c["include"])) if c.get("include") else "",
                ("<dt>Exclude</dt><dd>%s</dd>" % esc(c["exclude"])) if c.get("exclude") else "",
                ("<b>%s</b>%s%s" % (esc(dd["decision"]), (": " + esc(dd["reason"])) if dd.get("reason") else "", (" (%s)" % esc(dd["decided_by"])) if dd.get("decided_by") else ""))
                if dd else "Pending: the researchers refine and recode, or drop (<code>human.py low-alpha</code>)."))
        a('<h3>Codes at or above %s</h3><p>%s</p>' % (high, esc(", ".join("%s %s" % (c, labels.get(c, "")) for c in hi) or "none")))
        if len(d["conds"]) > 1:
            names = {"L": "Lite coding", "LJ": "screened, v0", "LJA": "after adversaries, v1", "LA": "after adversaries, v1"}
            a('<h3>Across conditions</h3><div class="scroll"><table><thead><tr><th>Condition</th><th class="n">Median alpha</th><th class="n">Min</th>'
              '<th class="n">Below %s</th><th class="n">At or above %s</th><th class="n">Cross-family kappa</th><th class="n">Survival</th></tr></thead><tbody>' % (floor, high))
            for cnd, s in d["conds"].items():
                a('<tr><td>%s (%s)</td><td class="n">%s</td><td class="n">%s</td><td class="n">%d</td><td class="n">%s</td><td class="n">%s</td><td class="n">%s</td></tr>' % (
                    esc(cnd), esc(names.get(cnd, "")), fmt(s.get("alpha_median")), fmt(s.get("alpha_min")), len(s.get("codes_dropped_alpha_below_floor") or []),
                    s.get("n_codes_alpha_at_or_above_%s" % t["alpha_high"], "n/a"), fmt(s.get("cross_family_kappa_median")), esc((s.get("survival") or {}).get("rate_pairs"))))
            a('</tbody></table></div><p class="note">In Full, agreement after the adversaries is agreement among coder-adversary pipelines, not among independent coders.</p>')
        a('<details><summary>Table: alpha and kappa per code</summary><div class="scroll"><table><thead><tr><th>Code</th><th>Label</th><th class="n">alpha</th>'
          '<th class="n">mean cross-family kappa</th><th class="n">any coder</th><th class="n">consensus</th><th>Status</th></tr></thead><tbody>')
        for c in codes:
            r = rel.get(c["id"], {})
            a('<tr><td>%s</td><td>%s</td><td class="n">%s</td><td class="n">%s</td><td class="n">%s</td><td class="n">%s</td><td>%s</td></tr>' % (
                esc(c["id"]), esc(c["label"]), fmt(r.get("alpha")), fmt(r.get("kappa_cross_family_mean")), esc(r.get("n_any")), esc(r.get("n_consensus")),
                status_badge(c["id"], summ, dec)))
        a('</tbody></table></div></details></section>')

    # prevalence
    a('<section id="prevalence" aria-labelledby="h-prev"><h2 id="h-prev">Prevalence per code</h2>')
    if prev:
        base = summ.get("prevalence_base") or 0
        ret = [r for r in prev.values() if r["status"] == "retained"]
        ret.sort(key=lambda r: -int(r["n_units"]))
        vmax = max([float(r["pct_units"]) for r in ret] + [1.0])
        vmax = min(100.0, max(10.0, (int(vmax / 10) + 1) * 10))
        a('<p class="note" style="margin-top:0">Share of the %d %s left after issue-coded units, assigned at consensus (%s), retained codes only.</p>' % (
            base, esc(cfg.study["unit_name_plural"]), esc(summ.get("consensus_rule"))))
        a(bar_chart([(r["code"], r["label"], float(r["pct_units"]), "%s %s: %s units, %s%%" % (r["code"], r["label"], r["n_units"], r["pct_units"])) for r in ret],
                    vmax, fmt_v=lambda v: "%.1f%%" % v, label="Prevalence per retained code, percent of units"))
        a(axis(vmax, [round(vmax * i / 4, 1) for i in range(5)]))
        a('<details><summary>Table: prevalence of every code</summary><div class="scroll"><table><thead><tr><th>Code</th><th>RQ</th><th>Label</th>'
          '<th class="n">Units</th><th class="n">%%</th><th class="n">Pending spot-check</th><th>Status</th></tr></thead><tbody>')
        for r in prev.values():
            a('<tr><td>%s</td><td>%s</td><td>%s</td><td class="n">%s</td><td class="n">%s</td><td class="n">%s</td><td>%s</td></tr>' % (
                esc(r["code"]), esc(r["rq"]), esc(r["label"]), esc(r["n_units"]), esc(r["pct_units"]), esc(r.get("n_pending_spot_check", 0)),
                status_badge(r["code"], summ, dec)))
        a('</tbody></table></div></details>')
        a('<p class="note">Issue-coded units at consensus: %d. Units with content no code covers (UNCOVERED, any coder): %d.</p>' % (
            summ.get("n_issue_units_consensus", 0), summ.get("n_uncovered_any_coder", 0)))
    else:
        a('<p class="empty">No coding results yet.</p>')
    a('</section>')

    # codebook
    a('<section id="codebook" aria-labelledby="h-cb"><h2 id="h-cb">The codebook (version %s)</h2>' % esc(ap.get("version", "n/a")))
    if not codes:
        a('<p class="empty">Not approved yet.</p>')
    for rq, q in cfg.rqs.items():
        cs = [c for c in codes if c.get("rq") == rq]
        if not cs:
            continue
        a('<h3>%s %s</h3>' % (esc(rq), esc(q["text"])))
        for c in cs:
            r, pv = rel.get(c["id"], {}), prev.get(c["id"], {})
            a('<div class="code"><h3>%s %s</h3><div class="meta"><span>%s</span><span>alpha %s</span><span>%s units at consensus</span><span>found by %s</span></div>' % (
                esc(c["id"]), esc(c["label"]), status_badge(c["id"], summ, dec) if summ else "", fmt(r.get("alpha")), esc(pv.get("n_units", "n/a")),
                esc(("analysts " + ", ".join(c.get("analysts") or [])) if c.get("analysts") else ("an adversary, admitted at review" if c.get("adopted_from_adversary") else "review"))))
            a('<dl><dt>Definition</dt><dd>%s</dd>%s%s</dl>' % (esc(c.get("definition")), ("<dt>Include</dt><dd>%s</dd>" % esc(c["include"])) if c.get("include") else "",
                                                             ("<dt>Exclude</dt><dd>%s</dd>" % esc(c["exclude"])) if c.get("exclude") else ""))
            seen = set()
            for qq in c.get("anchor_quotes") or []:
                if qq.get("uid") in seen or len(seen) >= 3:
                    continue
                seen.add(qq.get("uid"))
                a('<blockquote>&ldquo;%s&rdquo;<span class="uid">%s</span></blockquote>' % (esc(qq.get("quote")), esc(qq.get("uid"))))
            a('</div>')
    a('</section>')

    # human checks
    a('<section id="human" aria-labelledby="h-hu"><h2 id="h-hu">Human checks</h2><ul>')
    hc = d["heldout"]
    a('<li>Held-out sample: %s</li>' % ("pooled kappa <b>%s</b> between the researchers\' resolved labels and council consensus, over %d units and %d codes (median per-code kappa %s)." % (
        fmt(hc.get("pooled_kappa")), hc.get("n_units", 0), hc.get("n_codes_scored", 0), fmt(hc.get("median_kappa_per_code"))) if hc else "not yet scored."))
    sr = d["spot"]
    if sr is not None:
        no = [r for r in sr if (r.get("keep") or "").strip().lower() in ("n", "no", "0", "false", "remove")]
        a('<li>Spot-check: %d rows checked; %d not kept%s.</li>' % (len(sr), len(no), (": " + esc("; ".join("%s %s" % (r.get("uid"), r.get("code")) for r in no))) if no else ""))
    else:
        a('<li>Spot-check: not yet returned.</li>')
    a('<li>Blind pass: %d %s; codes the council lacked: %s.</li>' % (len(d["splits"].get("blind_pass", [])), esc(cfg.study["unit_name_plural"]),
                                                                    esc("; ".join(rv.get("blind_pass_codes_missing") or []) or "none recorded")))
    a('</ul></section>')

    # cost
    a('<section id="cost" aria-labelledby="h-cost"><h2 id="h-cost">Calls, tokens and cost by stage</h2>')
    cost = d["cost"]
    for kind, title in (("llm", "Model calls (analysts, adversaries, reconciler, coders)"), ("dm", "Decision-model requests")):
        rows = cost[kind]
        a('<h3>%s</h3>' % title)
        if not rows:
            a('<p class="empty">None.</p>')
            continue
        a('<div class="scroll"><table><thead><tr><th>Stage</th><th class="n">%s</th><th class="n">Input tokens</th><th class="n">Output tokens</th><th class="n">Cost (USD)</th></tr></thead><tbody>' % (
            "Calls" if kind == "llm" else "Requests"))
        tot = [0, 0, 0, 0.0, True]
        for s, r in rows:
            a('<tr><td>%s</td><td class="n">%d</td><td class="n">%s</td><td class="n">%s</td><td class="n">%s</td></tr>' % (
                esc(s), r["calls"], "{:,}".format(r["input"]), "{:,}".format(r["output"]), ("%.2f" % r["cost"]) if r["priced"] else "unpriced"))
            tot[0] += r["calls"]; tot[1] += r["input"]; tot[2] += r["output"]; tot[3] += r["cost"]; tot[4] &= r["priced"]
        a('<tr><th>Total</th><th class="n">%d</th><th class="n">%s</th><th class="n">%s</th><th class="n">%s</th></tr></tbody></table></div>' % (
            tot[0], "{:,}".format(tot[1]), "{:,}".format(tot[2]), ("%.2f" % tot[3]) + ("" if tot[4] else " (some unpriced)")))
    if cost["estimated"]:
        a('<p class="note">Token counts of manually answered or replayed calls are estimates (about 4 characters per token); costs use the list prices in the config (`prices`).</p>')
    a('</section>')
    a('<p class="note">Built by <code>council.py dashboard</code> from the files in this workspace. Nothing on this page is loaded from the network.</p>')
    a('</div><script>%s</script></body></html>' % JS)
    return "".join(P)


def write() -> "Path":
    out = M.W / "dashboard.html"
    out.write_text(build(), encoding="utf-8")
    return out
