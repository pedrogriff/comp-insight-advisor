"""Grounds the brief's options in retrieved policy clauses and interview notes.

Runs after assess_intervention_fit, before a model drafts the brief. With a retriever, the agent:

1. Retrieves the 3 clauses that govern each lever in any option, with a lever filter.
2. Checks that each limit the code applies, such as the 0.95 lift ceiling, appears in a clause
   for that lever. When the lever search missed the clause, an exact lookup adds it. When no
   clause states the limit, the brief reports a policy conflict instead of costing a stale rule.
3. Retrieves the one clause behind each checklist item the tool's flags raise.
4. Looks up every exit note for the cohort by metadata. It needs all of them, not the nearest five.

Without a retriever the function returns the same options and costs, and every checklist item
is unsupported, because no clause backs it. The two outputs side by side are the checkpoint 3.1
demonstration:
    python3 -m src.retrieval.grounded_options VP_CLOUD_AI RESEARCH_SCI --compare
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

from src.retrieval.embeddings import make_embedder
from src.retrieval.policy_search import PLAYBOOK_PATH, PolicyRetriever, check_limits
from src.tools.deterministic_analytics import DEFAULT_DB_PATH
from src.tools.intervention_fit import assess_intervention_fit
from src.tools.interview_search import NoteIndex, load_notes

# Checklist items: (name, lever filter, the agent's query to the playbook).
CHECKLIST_QUERIES = {
    "default_lever_mismatch": ("retention_grant", "what a retention grant does not fix base salary level departures"),
    "thin_driver_evidence": (None, "thin evidence fewer than 5 departures counts instead of percentages"),
    "compa_floor_breach": ("base_adjustment", "floor no base salary below compa-ratio"),
    "needs_calibration": ("level_review", "decision people manager calibration committee decide level"),
    "over_budget_base": ("base_adjustment", "funding adjustments above proactive remaining budget VP sign-off"),
}


def _clause(hit: dict[str, Any], added_by: str = "search") -> dict[str, Any]:
    return {"id": hit["id"], "heading": hit["heading"], "text": hit["text"], "levers": hit["levers"],
            "added_by": added_by}


def _facts(fit: dict[str, Any]) -> dict[str, str]:
    dep, by = fit["departures"]["total"], fit["departures"]["by_driver"]
    grant = next(lv for lv in fit["levers"] if lv["lever"] == "retention_grant")
    level = next(lv for lv in fit["levers"] if lv["lever"] == "level_review")
    option_c = next(o for o in fit["options"] if o["option"] == "C")
    return {
        "default_lever_mismatch": f"Retention grants address {grant['departures_addressed']} of {dep} departures.",
        "thin_driver_evidence": f"{dep} departures: {by['Level_Up_Offer']} level, {by['Base_Salary_Cap']} base salary, "
                                f"{by['Total_Equity_Size']} equity, {by['Cashflow_Year1_Gap']} first-year cash.",
        "compa_floor_breach": f"{fit['governance']['compa_floor_breaches']} employees sit below the floor, "
                              f"${fit['governance']['compa_floor_fix_usd']:,} to fix.",
        "needs_calibration": f"{level['candidates']} level review candidates, ${level['annual_cost_usd']:,} a year.",
        "over_budget_base": f"Option C costs ${option_c['first_year_cost_usd']:,.0f}, "
                            f"${option_c['budget_gap_usd']:,.0f} over the remaining budget.",
    }


def ground_options(vp_org_code: str, job_family: str, policy: PolicyRetriever | None = None,
                   notes: NoteIndex | None = None, db_path: Path = DEFAULT_DB_PATH, k: int = 3) -> dict[str, Any]:
    fit = assess_intervention_fit(vp_org_code, job_family, db_path)
    drivers = [d for d, n in fit["departures"]["by_driver"].items() if n]
    in_play = [lv["lever"] for lv in fit["levers"] if any(lv["lever"] in o["levers"] for o in fit["options"])]

    clauses: dict[str, list[dict[str, Any]]] = {}
    limits: dict[str, list[dict[str, Any]]] = {}
    conflicts: list[str] = []
    for lever in in_play:
        hits = [_clause(h) for h in policy.retrieve_for_lever(lever, drivers, k=k)] if policy else []
        checks = check_limits(lever, hits)
        for check in checks:
            if check["ok"]:
                continue
            if policy:
                extra = next((c for c in policy.chunks if lever in c["levers"] and check["value"] in c["text"]), None)
                if extra:
                    hits.append(_clause(extra, added_by="limit_check"))
                    check.update(found_in=extra["id"], ok=True, added_by="limit_check")
                    continue
                conflicts.append(f"The code applies {check['limit']} = {check['value']} for {lever}, "
                                 f"but no {lever} clause in the playbook states it.")
        clauses[lever], limits[lever] = hits, checks

    facts = _facts(fit)
    raised = dict(fit["flags"])
    raised["over_budget_base"] = any("base_adjustment" in o["levers"] and not o["fits_remaining_budget"]
                                     for o in fit["options"])
    checklist = []
    for name, (lever, query) in CHECKLIST_QUERIES.items():
        if not raised.get(name):
            continue
        hit = policy.search(query, k=1, filters={"levers": lever} if lever else None, min_coverage=0.0) if policy else []
        checklist.append({"item": name, "fact": facts[name], "clause": _clause(hit[0]) if hit else None,
                          "status": "cited" if hit else "unsupported"})

    exit_notes = []
    if notes is not None:
        found = notes.search("", k=10, filters={"note_type": "exit", "vp_org_code": vp_org_code,
                                                "job_family": job_family})
        exit_notes = [{"note_id": n["note_id"], "themes": n["themes"], "text": n["text"]} for n in found]

    return {
        "scope": fit["scope"],
        "retrieval": policy is not None,
        "options": [{key: o[key] for key in ("option", "name", "levers", "departures_addressed", "departures",
                                             "first_year_cost_usd", "fits_remaining_budget", "budget_gap_usd")}
                    for o in fit["options"]],
        "flags": fit["flags"],
        "clauses": clauses,
        "limits": limits,
        "policy_conflicts": conflicts,
        "checklist": checklist,
        "exit_notes": exit_notes,
        "unsupported": sum(1 for item in checklist if item["status"] == "unsupported"),
    }


def _summary(ctx: dict[str, Any]) -> list[str]:
    lines = [f"{'With' if ctx['retrieval'] else 'Without'} retrieval: {ctx['scope']['vp_org_code']} "
             f"{ctx['scope']['job_family']}"]
    for o in ctx["options"]:
        lines.append(f"  Option {o['option']}: {o['departures_addressed']} of {o['departures']} departures, "
                     f"${o['first_year_cost_usd']:,.0f}, {'fits' if o['fits_remaining_budget'] else 'over'} budget")
    for lever, hits in ctx["clauses"].items():
        lines.append(f"  {lever}: {', '.join(h['id'] + ('*' if h['added_by'] != 'search' else '') for h in hits) or 'no clause'}")
    for item in ctx["checklist"]:
        cite = f"{item['clause']['id']}: {item['clause']['text'][:70]}" if item["clause"] else "UNSUPPORTED, no clause"
        lines.append(f"  [{item['item']}] {item['fact']} -> {cite}")
    lines.append(f"  Exit notes: {', '.join(n['note_id'] for n in ctx['exit_notes']) or 'none'}")
    lines.append(f"  Policy conflicts: {len(ctx['policy_conflicts'])}. Unsupported checklist items: {ctx['unsupported']}")
    lines += [f"  CONFLICT: {c}" for c in ctx["policy_conflicts"]]
    return lines


if __name__ == "__main__":
    args = sys.argv[1:]
    valued = ("--embedder", "--playbook", "--index")
    opt = {a: args[i + 1] for i, a in enumerate(args) if a in valued and i + 1 < len(args)}
    positional = [a for i, a in enumerate(args) if not a.startswith("--") and (i == 0 or args[i - 1] not in valued)]
    org, family = positional[:2] if len(positional) >= 2 else ("VP_CLOUD_AI", "RESEARCH_SCI")
    retriever = PolicyRetriever(make_embedder(opt.get("--embedder")), path=Path(opt.get("--playbook", PLAYBOOK_PATH)),
                                index_path=opt.get("--index"))
    grounded = ground_options(org, family, retriever, NoteIndex(load_notes()))
    if "--json" in args:
        print(json.dumps(grounded, indent=2))
    elif "--compare" in args:
        print("\n".join(_summary(ground_options(org, family)) + [""] + _summary(grounded)))
    else:
        print("\n".join(_summary(grounded)))
