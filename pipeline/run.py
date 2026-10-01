#!/usr/bin/env python3
"""
Run the model stages of the council, in order. Deterministic work is done by council.py; every
model call goes through models.py; every decision-model call through models.decide().

  discovery            Stage 1: three analysts x research questions (x blocks), provenance check with up
                       to `max_repairs` repair rounds and one completeness round per reading, merge per
                       analyst, validate, freeze v0
  discovery-adversary  Stage 1, Full: decision-model grounding and omission leads on v0; one cross-family
                       adversary per analyst; the analyst answers; v1 = v0 + delta; provenance check of v1
  reconcile            Stage 2: per research question, reconciler (Lite) + reconciliation adversary and
                       reconciler answers (Full); support floor; candidate codebook. In Full the Lite
                       baseline (on discovery v0) also runs unless reconciliation.run_lite_baseline_in_full
                       is false.
  code                 Stage 4: Lite coding (every code shown) -> coding/L. Full adds decision-model
                       screening -> coding/LJ, freeze, coding adversaries with decision-model leads and the
                       coders' answers -> coding/LJA (without a decision model: adversaries on L -> coding/LA).
                       Then Stage 5 consensus for every condition.

Stops where humans take over: after `reconcile` (author review) and before `code` (approved codebook).
With the `manual` backend, calls without a reply leave their prompt in <workspace>/manual/ and the
command exits with status 3; answer the prompts and run the same command again. Every step skips work
whose output already exists, so a command can be rerun after an interruption.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import council as K  # noqa: E402
import models  # noqa: E402
import prompts as P  # noqa: E402

PENDING = []
REPAIRS_LOCK = threading.Lock()


def guarded(fn, *a, **kw):
    """Run fn; a manual-backend call without a reply is recorded, not raised."""
    try:
        return fn(*a, **kw)
    except models.ManualPending as e:
        PENDING.append(str(e))
        return None


def pmap(fn, items, workers=None):
    with ThreadPoolExecutor(int(workers or K.cfg.d["workers"])) as ex:
        return list(ex.map(lambda it: guarded(fn, it), items))


def stop_if_pending():
    if PENDING:
        print("\n%d prompts are waiting for a reply (manual backend):" % len(PENDING))
        for p in sorted(set(PENDING))[:50]:
            print("   %s" % p)
        print("Write each reply (the JSON the prompt asks for) next to its prompt as <name>.reply.json, then rerun this command.")
        sys.exit(3)


def corpus_input():
    return ("data/corpus.txt", K.W / "data" / "corpus.txt")


def code_view(c: dict) -> dict:
    v = OrderedDict((k, c.get(k, "")) for k in ("label", "definition", "include", "exclude"))
    if K.cfg.d["decision_model"].get("include_research_question", True) and c.get("rq") in K.cfg.rqs:
        v["research_question"] = K.cfg.rqs[c["rq"]]["text"]
    return v


def dm_question() -> str:
    text = (K.C.PROMPTS / "decision_model_questions.md").read_text(encoding="utf-8")
    q = text.split("<!-- BEGIN QUESTION code_applies -->", 1)[1].split("<!-- END QUESTION code_applies -->", 1)[0].strip()
    s = K.cfg.study
    topic = (s.get("topic_phrase") or "").rstrip()
    if topic and not topic.startswith(" "):
        topic = " " + topic
    return q.replace("{{UNIT}}", s["unit_name"]).replace("{{RESPONDENT}}", s["respondent_name"]).replace("{{TOPIC}}", topic)


def dm_state(r: dict) -> dict:
    st = OrderedDict([(K.cfg.d["decision_model"].get("state_key") or "unit_text", r["text"])])
    if (r.get("context") or "").strip():
        st["context"] = r["context"]
    return st


# --------------------------------------------------------------------------- Stage 1: provenance repairs
def repair_hints(errs, d, corpus):
    hints = []
    for e in errs:
        m = re.match(r"^(\S+): quote not verbatim for (\S+) ", e)
        if not m:
            continue
        code_id, uid = m.group(1), m.group(2)
        for q in [q for c in d.get("codes", []) if c.get("id") == code_id for q in c.get("anchor_quotes", []) if str(q.get("uid")) == uid]:
            where = [u for u, row in corpus.items() if u != uid and K.quote_status(q.get("quote", ""), row["text"]) == "exact"]
            hints.append("- %s: the quote attributed to %s " % (code_id, uid) +
                         ("occurs verbatim in %s, not %s." % (", ".join(where[:3]), uid) if where else
                          "does not occur verbatim in it; copy the exact characters or choose another quote."))
    return (["", "Where the program found the quotes:"] + hints) if hints else []


def validate_reading(job, corpus, completeness_done: bool, repairs: int, expected=None):
    """One provenance pass over a v0 reading; returns 'pass' | 'repair' | 'complete' | 'fail' and the next instruction."""
    path = K.W / job["output"]
    d = K.read_json(path)
    errs, warns, stats = K.validate_discovery(d, corpus, job["analyst"], expected=expected)
    missing = stats["units_neither_coded_nor_uncodeable"]
    if not errs and missing and not completeness_done:
        return "complete", P.instruction("01_discovery_analyst.md", "completeness", {
            "N_ACCOUNTED": stats["n_units_covered"] + stats["n_uncodeable"], "N_UNITS": len(expected or corpus),
            "OUTPUT_PATH": job["output"], "UNIT_IDS": ", ".join(missing)}), stats
    if not errs:
        return "pass", None, stats
    if repairs >= int(K.cfg.d["max_repairs"]):
        return "fail", errs, stats
    return "repair", P.instruction("01_discovery_analyst.md", "repair", {
        "OUTPUT_PATH": job["output"], "ERRORS": "\n".join("- " + e for e in errs) + "\n".join(repair_hints(errs, d, corpus))}), stats


def run_reading(job):
    """Discovery call for one reading, then the provenance check with repairs and one completeness round."""
    corpus = K.load_corpus()
    fam = K.cfg.analysts[job["analyst"]]
    inputs = [(job["corpus_label"], job["corpus_path"])]
    batch = job["tag"]
    if not (K.W / job["output"]).exists():
        models.call(stage="discovery", role="analyst-%s" % job["analyst"], family=fam, brief=job["brief"], inputs=inputs,
                    outputs=[job["output"]], batch=batch)
    rec = K.rj(K.W / "discovery" / "validation" / "per_reading" / ("%s.json" % job["tag"]))
    completeness, repairs, unaccounted = rec.get("completeness_round", False), rec.get("repairs", 0), rec.get("units_unaccounted_before")
    while True:
        status, nxt, stats = validate_reading(job, corpus, completeness, repairs, expected=job["units"])
        if status in ("pass", "fail"):
            break
        # The round is recorded only after its reply has been applied, so that a manual run that stops
        # here (exit 3) asks for, and later reads, the same numbered call when it is rerun.
        attempt = repairs + int(completeness) + 1
        models.call(stage="discovery-repair", role="analyst-%s" % job["analyst"], family=fam, brief=job["brief"],
                    inputs=inputs + [(job["output"], K.W / job["output"])], outputs=[job["output"]], batch=batch, instruction=nxt,
                    attempt=attempt)
        if status == "complete":
            completeness, unaccounted = True, stats["n_units_neither_coded_nor_uncodeable"]
        else:
            repairs += 1
        rec = OrderedDict([("status", "IN_REPAIR"), ("repairs", repairs), ("completeness_round", completeness), ("units_unaccounted_before", unaccounted)])
        K.write_json(K.D("discovery", "validation", "per_reading", "%s.json" % job["tag"]), rec)
    out = OrderedDict([("status", status.upper()), ("repairs", repairs), ("completeness_round", completeness),
                       ("units_unaccounted_before", unaccounted),
                       ("units_unaccounted_after", stats["n_units_neither_coded_nor_uncodeable"]), ("n_codes", stats["n_codes"]),
                       ("errors", nxt if status == "fail" else [])])
    K.write_json(K.D("discovery", "validation", "per_reading", "%s.json" % job["tag"]), out)
    return job["tag"], out


def cmd_discovery(args):
    if not (K.W / "data" / "corpus.csv").exists():
        K.cmd_prepare(argparse.Namespace(force=False))
    jobs = K.reading_jobs()
    if args.only:
        jobs = [j for j in jobs if j["analyst"] in args.only.split(",")]
    res = dict(r for r in pmap(run_reading, jobs) if r)
    stop_if_pending()
    summ = K.rj(K.W / "discovery" / "validation" / "repairs.json")
    summ.update(res)
    K.write_json(K.D("discovery", "validation", "repairs.json"), OrderedDict(sorted(summ.items())))
    for k, v in sorted(res.items()):
        print("%s: %s, %s codes, %s repairs, unaccounted before/after completeness %s/%s" % (
            k, v["status"], v["n_codes"], v["repairs"], v["units_unaccounted_before"], v["units_unaccounted_after"]))
    if any(v["status"] != "PASS" for v in res.values()):
        sys.exit("a discovery reading did not pass the provenance check after %s repairs; see discovery/validation/per_reading/. "
                 "Nothing with an error goes forward to reconciliation." % K.cfg.d["max_repairs"])
    for L in sorted({j["analyst"] for j in jobs}):
        K.merge_readings(L)
    if args.only:
        return
    if K.cmd_validate(argparse.Namespace(stage="v0")):
        sys.exit("merged v0 files did not pass validation")
    K.cmd_freeze(argparse.Namespace(what="discovery"))
    print("discovery: v0 frozen. Next: %s" % ("run.py discovery-adversary" if K.cfg.full else "run.py reconcile"))


# --------------------------------------------------------------------------- Stage 1, Full
def jev_leads(L: str):
    """Decision-model grounding (cited pairs) and omission (uncited pairs) scores on analyst L's v0 file."""
    corpus = K.load_corpus()
    d = K.read_json(K.W / "discovery" / "v0" / ("analyst_%s.json" % L))
    codes = [c for c in d["codes"] if isinstance(c, dict)]
    gfile, ofile = K.W / "discovery" / "jev" / ("grounding_%s.json" % L), K.W / "discovery" / "jev" / ("omission_%s.json" % L)
    if gfile.exists() and ofile.exists():
        return
    q = dm_question()
    qs = {c["id"]: {"code": code_view(c), "question": q} for c in codes}

    def score(u):
        return u, models.decide(dm_state(corpus[u]), qs, stage="jev-leads", role="analyst-%s" % L, batch=u)

    sc = dict(r for r in pmap(score, list(corpus), K.cfg.d["decision_model"].get("workers", 8)) if r)
    if len(sc) < len(corpus):
        return  # requests still waiting (manual backend): write nothing until every unit is scored
    cited = {c["id"]: list(dict.fromkeys(str(x) for x in c.get("participants") or [])) for c in codes}   # ordered: prompts must not depend on hash order
    pairs = [{"code_id": cid, "uid": u, "p": sc[u].get(cid)} for cid, us in cited.items() for u in us if u in sc]
    lo, hi = float(K.cfg.t["grounding_lead_below"]), float(K.cfg.t["omission_lead_at_or_above"])
    g = sorted([x for x in pairs if x["p"] is not None and x["p"] < lo], key=lambda x: x["p"])
    o = sorted([{"code_id": cid, "uid": u, "p": p} for u, row in sc.items() for cid, p in row.items()
                if p is not None and p >= hi and u not in cited.get(cid, set())], key=lambda x: -x["p"])
    K.write_json(gfile, OrderedDict([("analyst", L), ("question", q), ("threshold_below", lo), ("n_pairs", len(pairs)),
                                     ("n_leads", len(g)), ("leads", g), ("all", pairs)]))
    K.write_json(ofile, OrderedDict([("analyst", L), ("question", q), ("threshold_at_or_above", hi), ("n_leads", len(o)), ("leads", o)]))
    print("decision-model leads %s: %d of %d cited pairs below %s; %d uncited pairs at or above %s" % (L, len(g), len(pairs), lo, len(o), hi))


def scopes():
    """Adversary scopes: the whole corpus, or each block when the corpus is split."""
    bl = K.blocks()
    if len(bl) == 1 and not bl[0]["id"]:
        return [OrderedDict([("id", None), ("label", "data/corpus.txt"), ("units", bl[0]["units"])])]
    return [OrderedDict([("id", b["id"]), ("label", "data/blocks/%s.txt" % b["id"]), ("units", b["units"])]) for b in bl]


def scoped_v0(L, sc):
    """v0 restricted to one block's codes (blocks only)."""
    d = K.read_json(K.W / "discovery" / "v0" / ("analyst_%s.json" % L))
    if not sc["id"]:
        return K.W / "discovery" / "v0" / ("analyst_%s.json" % L)
    us = set(sc["units"])
    part = OrderedDict(d, codes=[c for c in d["codes"] if c.get("block") == sc["id"]], n_read=len(sc["units"]),
                       uncodeable=[u for u in d.get("uncodeable", []) if u in us])
    p = K.D("discovery", "v0_scoped", "analyst_%s_%s.json" % (L, sc["id"]))
    K.write_json(p, part)
    return p


def adversary_and_answer(job):
    L, sc = job
    sfx = "" if not sc["id"] else "_%s" % sc["id"]
    corpus = K.load_corpus()
    v = K.vocab(corpus)
    v0 = scoped_v0(L, sc)
    v0_label = "discovery/v0/analyst_%s.json" % L
    ch_name = "discovery/challenges/adversary_%s%s.json" % (L, sfx)
    gl, ol = "discovery/jev/grounding_%s.json" % L, "discovery/jev/omission_%s.json" % L
    leads = K.cfg.decision_model_on
    first_code = next((c["id"] for c in K.read_json(v0)["codes"]), "%s-01" % L)
    vals = dict(v, ANALYST=L, CORPUS_FILE=sc["label"], N_UNITS=len(sc["units"]), V0_FILE=v0_label, GROUNDING_FILE=gl, OMISSION_FILE=ol,
                GROUNDING_BELOW=K.cfg.t["grounding_lead_below"], OMISSION_AT_OR_ABOVE=K.cfg.t["omission_lead_at_or_above"],
                OUTPUT_PATH="discovery/challenges/adversary_%s.json" % L, EXAMPLE_CODE_ID=first_code, EXAMPLE_UID=sc["units"][0], LEADS=leads,
                CHALLENGES_FILE="discovery/challenges/adversary_%s.json" % L, ANSWERS_PATH="discovery/answers/answer_%s.json" % L,
                DELTA_PATH="discovery/v1_delta/analyst_%s.json" % L)
    adv_brief = P.write("01_discovery_adversary.md", vals, K.D("briefs", "discovery", "adversary_%s%s.md" % (L, sfx)))
    ans_brief = P.write("01_discovery_answer.md", vals, K.D("briefs", "discovery", "answer_%s%s.md" % (L, sfx)))
    inputs = [(sc["label"], K.W / sc["label"]), (v0_label, v0)]
    if leads:
        inputs += [(gl, K.W / gl), (ol, K.W / ol)]
    if not (K.W / ch_name).exists():
        models.call(stage="discovery-adversary", role="adversary-of-%s" % L, family=K.cfg.analyst_adversary[L], brief=adv_brief,
                    inputs=inputs, outputs=[(vals["OUTPUT_PATH"], ch_name)], batch=sc["id"] or "-")
    dname = "discovery/v1_delta/analyst_%s%s.json" % (L, sfx)
    if not (K.W / dname).exists():
        models.call(stage="discovery-answer", role="analyst-%s-answers" % L, family=K.cfg.analysts[L], brief=ans_brief,
                    inputs=[(sc["label"], K.W / sc["label"]), (v0_label, v0), (vals["CHALLENGES_FILE"], K.W / ch_name)],
                    outputs=[(vals["ANSWERS_PATH"], "discovery/answers/answer_%s%s.json" % (L, sfx)), (vals["DELTA_PATH"], dname)],
                    batch=sc["id"] or "-")
    return L, sc["id"], ans_brief


def combine_scoped(L, scs):
    """Blocks only: join per-block challenge, answer and delta files into the per-analyst files."""
    if len(scs) == 1 and not scs[0]["id"]:
        return
    ch = OrderedDict([("adversary_for", L), ("axes", ["semantic", "latent", "contrastive"]), ("challenges", []), ("quarantined_codes", []), ("notes", [])])
    an = OrderedDict([("analyst", L), ("answers", [])])
    de = OrderedDict([("replace", []), ("remove", []), ("uncodeable_add", []), ("uncodeable_remove", [])])
    for sc in scs:
        s = sc["id"]
        c = K.rj(K.W / "discovery" / "challenges" / ("adversary_%s_%s.json" % (L, s)))
        for x in c.get("challenges", []):
            x["id"] = "%s-%s" % (s, x.get("id"))
            ch["challenges"].append(x)
        for x in c.get("quarantined_codes") or []:
            x["block"] = s
            ch["quarantined_codes"].append(x)
        if c.get("notes"):
            ch["notes"].append("%s: %s" % (s, c["notes"]))
        for x in K.rj(K.W / "discovery" / "answers" / ("answer_%s_%s.json" % (L, s))).get("answers", []):
            x["challenge_id"] = "%s-%s" % (s, x.get("challenge_id"))
            an["answers"].append(x)
        dd = K.rj(K.W / "discovery" / "v1_delta" / ("analyst_%s_%s.json" % (L, s)))
        for k in de:
            de[k] += [dict(x, block=x.get("block") or s) if k == "replace" and isinstance(x, dict) else x for x in dd.get(k) or []]
    ch["notes"] = " | ".join(ch["notes"])
    K.write_json(K.W / "discovery" / "challenges" / ("adversary_%s.json" % L), ch)
    K.write_json(K.W / "discovery" / "answers" / ("answer_%s.json" % L), an)
    K.write_json(K.W / "discovery" / "v1_delta" / ("analyst_%s.json" % L), de)


def repair_v1(L, ans_brief):
    """Provenance check of v1 with repairs (as deltas) and one completeness round."""
    corpus = K.load_corpus()
    name = "discovery/v1/analyst_%s.json" % L
    dname = "discovery/v1_delta/analyst_%s.json" % L
    statef = K.W / "discovery" / "validation" / ("v1_repairs_%s.json" % L)
    st = K.rj(statef)
    completeness, repairs, unaccounted = st.get("completeness_round", False), st.get("repairs", 0), st.get("units_unaccounted_before")
    while True:
        d = K.read_json(K.W / name)
        errs, warns, stats = K.validate_discovery(d, corpus, L)
        missing = stats["units_neither_coded_nor_uncodeable"]
        if not errs and missing and not completeness:
            completeness, unaccounted = True, len(missing)
            instr = P.instruction("01_discovery_answer.md", "completeness", {"V1_FILE": name, "N_ACCOUNTED": len(corpus) - len(missing),
                                                                             "N_UNITS": len(corpus), "DELTA_PATH": dname, "UNIT_IDS": ", ".join(missing)})
        elif not errs:
            break
        elif repairs >= int(K.cfg.d["max_repairs"]):
            break
        else:
            repairs += 1
            instr = P.instruction("01_discovery_answer.md", "repair", {"V1_FILE": name, "DELTA_PATH": dname,
                                                                       "ERRORS": "\n".join("- " + e for e in errs) + "\n".join(repair_hints(errs, d, corpus))})
        ins = [corpus_input()] if len(scopes()) == 1 else [(s["label"], K.W / s["label"]) for s in scopes()]
        attempt = repairs + int(completeness)          # already counts the round being requested
        stage_dname = dname.replace(".json", "_repair%d.json" % attempt)
        models.call(stage="discovery-answer-repair", role="analyst-%s-answers" % L, family=K.cfg.analysts[L], brief=ans_brief,
                    inputs=ins + [(name, K.W / name)], outputs=[(dname, stage_dname)], instruction=instr, attempt=attempt)
        K.write_json(K.W / name, K.apply_delta(K.read_json(K.W / name), K.read_json(K.W / stage_dname)))
        K.write_json(statef, OrderedDict([("repairs", repairs), ("completeness_round", completeness), ("units_unaccounted_before", unaccounted)]))
    with REPAIRS_LOCK:   # three analysts run in parallel; one read-modify-write at a time
        rep = K.rj(K.W / "discovery" / "validation" / "repairs.json")
        rep["v1_%s" % L] = OrderedDict([("status", "PASS" if not errs else "FAIL"), ("repairs", repairs), ("completeness_round", completeness),
                                        ("units_unaccounted_before", unaccounted), ("units_unaccounted_after", stats["n_units_neither_coded_nor_uncodeable"]),
                                        ("n_codes", stats["n_codes"])])
        K.write_json(K.D("discovery", "validation", "repairs.json"), OrderedDict(sorted(rep.items())))


def cmd_discovery_adversary(args):
    if not K.cfg.full:
        sys.exit("discovery adversaries are part of Full; this config is mode: lite")
    for L in K.cfg.analysts:
        v = K.W / "discovery" / "validation" / ("v0_analyst_%s.json" % L)
        if not v.exists() or K.read_json(v)["status"] != "PASS":
            sys.exit("discovery v0 for %s has not passed validation; run `run.py discovery` first" % L)
    if K.cfg.decision_model_on:
        for L in K.cfg.analysts:
            guarded(jev_leads, L)
        stop_if_pending()
    scs = scopes()
    res = [r for r in pmap(adversary_and_answer, [(L, s) for L in K.cfg.analysts for s in scs], workers=3 * len(scs)) if r]
    stop_if_pending()
    briefs = {}
    for L, sid, b in res:
        briefs.setdefault(L, b)
    for L in K.cfg.analysts:
        combine_scoped(L, scs)
        v1 = K.W / "discovery" / "v1" / ("analyst_%s.json" % L)
        if not v1.exists():
            K.write_json(v1, K.apply_delta(K.read_json(K.W / "discovery" / "v0" / ("analyst_%s.json" % L)),
                                           K.read_json(K.W / "discovery" / "v1_delta" / ("analyst_%s.json" % L))))
    pmap(lambda L: repair_v1(L, briefs[L]), list(K.cfg.analysts), workers=3)
    stop_if_pending()
    rc = K.cmd_validate(argparse.Namespace(stage="v1"))
    print("discovery-adversary: v1 written%s. Next: run.py reconcile" % ("" if not rc else " (validation FAILED; fix before reconciliation)"))


# --------------------------------------------------------------------------- Stage 2
def reconcile_one(cond, job):
    d, rel = job["dir"], lambda p: str(p.relative_to(K.W))
    if job["n_codes"] == 0:
        K.write_json(d / "merge_plan.json", {"groups": [], "relations": [], "notes": "no raw codes for this question"})
        if cond == "full":
            K.write_json(d / "merge_plan_revised.json", {"groups": [], "relations": []})
        return
    inp = ("reconciliation/input.json", job["input"])
    plan = d / "merge_plan.json"
    if not plan.exists():
        models.call(stage="reconcile", role="reconciler", family=K.cfg.reconciler, brief=job["brief"], inputs=[inp], batch="%s-%s" % (cond, job["rq"]),
                    outputs=[("reconciliation/merge_plan.json", rel(plan))])
    if cond != "full":
        return
    ch = d / "adversary_challenges.json"
    if not ch.exists():
        models.call(stage="reconcile-adversary", role="reconciliation-adversary", family=K.cfg.recon_adversary, brief=job["adversary_brief"],
                    inputs=[inp, ("reconciliation/merge_plan.json", plan)], batch=job["rq"],
                    outputs=[("reconciliation/adversary_challenges.json", rel(ch))])
    if not (d / "merge_plan_revised.json").exists():
        models.call(stage="reconcile-answer", role="reconciler-answers", family=K.cfg.reconciler, brief=job["answer_brief"],
                    inputs=[inp, ("reconciliation/merge_plan.json", plan), ("reconciliation/adversary_challenges.json", ch)], batch=job["rq"],
                    outputs=[("reconciliation/reconciler_answers.json", rel(d / "reconciler_answers.json")),
                             ("reconciliation/merge_plan_revised.json", rel(d / "merge_plan_revised.json"))])


def cmd_reconcile(args):
    conds = [args.cond] if args.cond else (["lite", "full"] if K.cfg.full and K.cfg.d["reconciliation"]["run_lite_baseline_in_full"] else [K.cfg.mode])
    for cond in conds:
        if cond == "full" and not K.cfg.full:
            sys.exit("Full reconciliation needs mode: full")
        jobs = K.reconcile_prepare(cond)
        pmap(lambda j: reconcile_one(cond, j), jobs)
        stop_if_pending()
        K.reconcile_apply(cond)
    print("reconcile: candidate codebook(s) written. STOP: Stage 3 is author review by researchers. "
          "Build the dashboard with `human.py review-dashboard` (after the researchers' blind pass).")


# --------------------------------------------------------------------------- Stage 4
def code_batch(cond, k, n, brief, batch_label, batch_path, stage):
    out = K.W / "coding" / cond / ("coder%s_batch%d.jsonl" % (k, n))
    if out.exists():
        return
    name = "coding/v0/coder%s_batch%d.jsonl" % (k, n)
    models.call(stage=stage, role="coder-%s" % k, family=K.cfg.coders[k], brief=brief, inputs=[(batch_label, batch_path)], batch=str(n),
                outputs=[(name, str(out.relative_to(K.W)))],
                instruction="Code every unit in batch %d. Return the file under the key `%s`." % (n, name))
    got = [json.loads(l).get("uid") for l in out.read_text(encoding="utf-8").splitlines() if l.strip().startswith("{")]
    want = K.batch_units(n)
    if set(got) != set(want):
        print("   ! coder %s batch %d: %d of %d units returned; consensus reports the gap" % (k, n, len(set(got) & set(want)), len(want)))


def code_lite():
    if not (K.W / "coding" / "batches" / "batches.json").exists():
        K.cmd_code_prepare(argparse.Namespace(batch_size=None))
    jobs = [(k, n) for k in K.cfg.coders for n in K.batch_ids()]
    pmap(lambda j: code_batch("L", j[0], j[1], K.W / "briefs" / "coding" / ("coder_%s.md" % j[0]),
                              "coding/batches/batch%d.txt" % j[1], K.W / "coding" / "batches" / ("batch%d.txt" % j[1]), "coding"), jobs)


def jev_screen(book):
    f = K.W / "coding" / "jev" / "screen.json"
    if f.exists():
        return K.read_json(f)["scores"]
    corpus = K.load_corpus()
    q = dm_question()
    qs = {c["id"]: {"code": code_view(c), "question": q} for c in book["codes"]}
    sc = dict(r for r in pmap(lambda u: (u, models.decide(dm_state(corpus[u]), qs, stage="jev-screen", role="coders", batch=u)),
                              list(corpus), K.cfg.d["decision_model"].get("workers", 8)) if r)
    stop_if_pending()
    K.write_json(f, OrderedDict([("question", q), ("model", K.cfg.d["decision_model"].get("model")), ("codes", list(qs)), ("scores", sc)]))
    print("jev-screen: %d units x %d codes" % (len(sc), len(qs)))
    return sc


def shown_codes(scores: dict, rng) -> tuple:
    t = K.cfg.t
    ranked = sorted(scores, key=lambda c: -(scores[c] or 0))
    shown = {c for c in ranked if (scores[c] or 0) >= float(t["screening_tau"])} | set(ranked[:int(t["screening_top_k"])])
    hidden = [c for c in ranked if c not in shown]
    audit = [c for c in hidden if rng.random() < float(t["screening_audit_share"])]
    return sorted(shown | set(audit)), sorted(audit)


def code_screened(book):
    sc = jev_screen(book)
    corpus = K.load_corpus()
    rng = random.Random(int(K.cfg.d["splits"]["seed"]))
    plan, audit = {}, []
    for u in corpus:
        plan[u], a = shown_codes(sc.get(u, {}), rng)
        audit += ["%s:%s" % (u, c) for c in a]
    t = K.cfg.t
    K.write_json(K.D("coding", "LJ", "screening_plan.json"), OrderedDict([
        ("tau_show", t["screening_tau"]), ("top_k", t["screening_top_k"]), ("audit_share", t["screening_audit_share"]),
        ("seed", K.cfg.d["splits"]["seed"]), ("n_pairs_shown", sum(len(v) for v in plan.values())),
        ("n_pairs_total", len(plan) * len(book["codes"])), ("audit_pairs", audit), ("shown", plan)]))
    nb = K.batch_ids()
    for n in nb:
        units = K.batch_units(n)
        lines = ["# Coding batch %d of %d: %d units (screened)" % (n, len(nb), len(units)), ""]
        for u in units:
            lines += [K.unit_text_block(u, corpus[u]), "Codes to consider for this unit: %s" % ", ".join(plan[u]), ""]
        K.D("coding", "LJ", "batches", "batch%d.txt" % n).write_text("\n".join(lines), encoding="utf-8")
        listed = {x for u in units for x in plan[u]}
        sub = dict(book, codes=[c for c in book["codes"] if c["id"] in listed])
        for k in K.cfg.coders:
            vals = dict(K.coding_values(book, corpus, len(nb), sub), CODER=k, SCREENING=True, LEADS=False,
                        OUTPUT_PATH="coding/v0/coder%s_batch<N>.jsonl" % k)
            P.write("04_coder.md", vals, K.D("briefs", "coding", "LJ", "coder_%s_batch%d.md" % (k, n)))
    jobs = [(k, n) for k in K.cfg.coders for n in nb]
    pmap(lambda j: code_batch("LJ", j[0], j[1], K.W / "briefs" / "coding" / "LJ" / ("coder_%s_batch%d.md" % j),
                              "coding/batches/batch%d.txt" % j[1], K.W / "coding" / "LJ" / "batches" / ("batch%d.txt" % j[1]), "coding-screened"), jobs)


def code_adversary(book):
    base, out = K.adversary_base(), K.adversary_cond()
    sc = K.read_json(K.W / "coding" / "jev" / "screen.json")["scores"] if K.cfg.decision_model_on else {}
    lo, hi = float(K.cfg.t["coding_lead_assigned_below"]), float(K.cfg.t["coding_lead_unassigned_at_or_above"])

    def one(job):
        k, n = job
        v0 = K.W / "coding" / base / ("coder%s_batch%d.jsonl" % (k, n))
        if not v0.exists():
            return
        rows = [json.loads(l) for l in v0.read_text(encoding="utf-8").splitlines() if l.strip()]
        leads = []
        for row in rows:
            got = set(row.get("codes") or [])
            for c, p in sc.get(row.get("uid"), {}).items():
                if p is None:
                    continue
                if c in got and p < lo:
                    leads.append({"uid": row["uid"], "code_id": c, "p": p, "lead": "assigned, low probability"})
                if c not in got and p >= hi:
                    leads.append({"uid": row["uid"], "code_id": c, "p": p, "lead": "not assigned, high probability"})
        lf = K.D("coding", out, "leads", "coder%s_batch%d.json" % (k, n))
        K.write_json(lf, {"coder": k, "batch": n, "leads": leads})
        ch = K.W / "coding" / out / "challenges" / ("coder%s_batch%d.json" % (k, n))
        batch = ("coding/batches/batch%d.txt" % n, K.W / "coding" / "batches" / ("batch%d.txt" % n))
        mine = ("coding/v0/coder%s_batch%d.jsonl" % (k, n), v0)
        ins = [batch, mine] + ([("coding/leads/coder%s_batch%d.json" % (k, n), lf)] if K.cfg.decision_model_on else [])
        if not ch.exists():
            models.call(stage="coding-adversary", role="adversary-of-coder-%s" % k, family=K.cfg.coder_adversary[k],
                        brief=K.W / "briefs" / "coding" / ("coding_adversary_%s.md" % k), inputs=ins, batch=str(n),
                        outputs=[("coding/challenges/coder%s_batch%d.json" % (k, n), str(ch.relative_to(K.W)))],
                        instruction="Batch %d." % n)
        if not (K.W / "coding" / out / ("coder%s_batch%d.jsonl" % (k, n))).exists():
            models.call(stage="coding-answer", role="coder-%s-answers" % k, family=K.cfg.coders[k],
                        brief=K.W / "briefs" / "coding" / ("coding_answer_%s.md" % k), batch=str(n),
                        inputs=[batch, mine, ("coding/challenges/coder%s_batch%d.json" % (k, n), ch)],
                        outputs=[("coding/answers/coder%s_batch%d.json" % (k, n), "coding/%s/answers/coder%s_batch%d.json" % (out, k, n)),
                                 ("coding/v1/coder%s_batch%d.jsonl" % (k, n), "coding/%s/coder%s_batch%d.jsonl" % (out, k, n))],
                        instruction="Batch %d." % n)

    pmap(one, [(k, n) for k in K.cfg.coders for n in K.batch_ids()])


def cmd_code(args):
    book = K.approved_book()
    code_lite()
    stop_if_pending()
    if K.cfg.full:
        if K.cfg.decision_model_on:
            code_screened(book)
            stop_if_pending()
        K.cmd_freeze(argparse.Namespace(what="coding"))
        code_adversary(book)
        stop_if_pending()
    else:
        K.cmd_freeze(argparse.Namespace(what="coding"))
    K.cmd_consensus(argparse.Namespace(cond=None))
    print("code: coding and consensus done. Next: human.py spot-check and heldout-score (researchers), then council.py report")


# --------------------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("discovery")
    p.add_argument("--only", help="comma-separated analysts; skips merge validation and freeze")
    sub.add_parser("discovery-adversary")
    p = sub.add_parser("reconcile")
    p.add_argument("--cond", choices=["lite", "full"])
    sub.add_parser("code")
    a = ap.parse_args(argv)
    K.init(a.config)
    models.configure(K.cfg)
    {"discovery": cmd_discovery, "discovery-adversary": cmd_discovery_adversary, "reconcile": cmd_reconcile, "code": cmd_code}[a.cmd](a)


if __name__ == "__main__":
    main()
