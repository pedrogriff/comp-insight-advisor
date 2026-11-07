"""Beam-search pruning validation and multi-cohort scaling benchmark for Checkpoint 4.1 feedback.

Answers two empirical questions raised in the Checkpoint 4.1 review:
1. On one cohort's 32 unique plans across 162 ordered paths, does a beam of width 3 preserve all
   three exhaustive brief options and the non-dominated frontier while cutting evaluated plans and
   model critic calls, and where do width 1 or width 2 miss higher-coverage or lower-cost plans?
2. When scaling to a 2-cohort VP org with 1,024 plans sharing one budget or a 3-cohort portfolio
   with 32,768 plans, do single-cohort search limits hold up directly, or must search factor into
   per-cohort width-3 beams followed by cross-cohort Pareto composition?

From the repo root:
    python3 -m src.planning.beam_validation
    python3 -m src.planning.beam_validation --org
"""

from __future__ import annotations

import itertools
import math
from pathlib import Path
import sys
from typing import Any

from src.planning.tot_planner import (ACTIONS, BEAM_WIDTH, COHORTS, MAX_EVALUATIONS, _money, choose_options,
                                      cohort_facts, dominated, evaluate, every_plan, outcome, search)
from src.tools.deterministic_analytics import DEFAULT_DB_PATH
from src.tools.intervention_fit import POLICY

VP_CLOUD_AI_COHORTS = [("VP_CLOUD_AI", "RESEARCH_SCI"), ("VP_CLOUD_AI", "AI_ML_ENG")]


def ordered_path_count() -> int:
    """Non-empty ordered lever sequences per cohort before duplicate-path pruning."""
    total, stack = 0, [()]
    while stack:
        plan = stack.pop()
        used = {lv for lv, _ in plan}
        for action in ACTIONS:
            if action[0] not in used:
                nxt = plan + (action,)
                total += 1
                stack.append(nxt)
    return total


def exhaustive_options(facts: dict[str, Any]) -> dict[str, Any]:
    """Ground-truth options and Pareto frontier across all 32 unique subset plans."""
    all_plans = every_plan(facts)
    nonempty = [p for p in all_plans if p["plan"] and (p["departures_addressed"] > 0 or p["declined_addressed"] > 0)]
    pareto = [e for e in nonempty if not dominated(e, nonempty)]
    return {
        "plans_evaluated": len(all_plans),
        "nonempty_plans": len(all_plans) - 1,
        "model_calls": len(all_plans) - 1,
        "pareto": pareto,
        "options": choose_options({"facts": facts, "nodes": nonempty}),
    }


def _budget_breakpoints(facts: dict[str, Any]) -> list[float]:
    costs = {p["first_year_cost_usd"] for p in every_plan(facts)}
    points = {0.0} | {c - 1.0 for c in costs if c > 0.0} | costs | {c + 1.0 for c in costs}
    return sorted(points)


def validate_cohort_beam(vp_org_code: str, job_family: str, widths: tuple[int, ...] = (1, 2, 3, 4),
                         db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    """Compare beam widths against exhaustive 32-plan evaluation on one cohort and across budgets."""
    facts = cohort_facts(vp_org_code, job_family, db_path)
    exh = exhaustive_options(facts)
    exh_opt_outcomes = [(o["role"], outcome(o)) for o in exh["options"]]
    exh_opt_sigs = [(o["role"], outcome(o), o["signature"]) for o in exh["options"]]
    breakpoints = _budget_breakpoints(facts)

    by_width: dict[int, dict[str, Any]] = {}
    for w in widths:
        tree = search(facts, width=w)
        opts = choose_options(tree)
        node_outcomes = {outcome(n) for n in tree["nodes"]}
        missed_pareto = [p for p in exh["pareto"] if outcome(p) not in node_outcomes]
        missed_options = [
            {"role": fo["role"], "beam": bo["signature"], "beam_outcome": outcome(bo),
             "exhaustive": fo["signature"], "exhaustive_outcome": outcome(fo)}
            for bo, fo in zip(opts, exh["options"]) if outcome(bo) != outcome(fo)
        ]

        sweep_misses = 0
        for bgt in breakpoints:
            f_bgt = {**facts, "remaining_budget_usd": bgt}
            exh_bgt = exhaustive_options(f_bgt)["options"]
            beam_bgt = choose_options(search(f_bgt, width=w))
            if [(o["role"], outcome(o)) for o in beam_bgt] != [(o["role"], outcome(o)) for o in exh_bgt]:
                sweep_misses += 1

        by_width[w] = {
            "evaluations": tree["evaluations"],
            "model_calls": tree["model_calls"],
            "rounds": len(tree["kept_by_depth"]),
            "kept_by_depth": tree["kept_by_depth"],
            "options": opts,
            "options_match": [(o["role"], outcome(o)) for o in opts] == exh_opt_outcomes,
            "signatures_match": [(o["role"], outcome(o), o["signature"]) for o in opts] == exh_opt_sigs,
            "missed_options": missed_options,
            "missed_pareto": missed_pareto,
            "budget_thresholds_tested": len(breakpoints),
            "budget_option_misses": sweep_misses,
        }

    return {
        "scope": f"{vp_org_code} {job_family}",
        "ordered_paths": ordered_path_count(),
        "exhaustive": exh,
        "by_width": by_width,
    }


def _non_budget_signs(entry: dict[str, Any]) -> frozenset[str]:
    return frozenset(s for s in entry["sign_offs"] if not s.startswith("VP, above"))


def composable_cohort_front(nodes: list[dict[str, Any]]) -> list[tuple[tuple[str, str], ...]]:
    """Cohort plans that no other evaluated node beats on coverage, cost and subset of sign-offs."""
    kept, seen = [], set()
    ordered = sorted(nodes, key=lambda x: (x["first_year_cost_usd"], len(x["plan"]), x["signature"]))
    for e in ordered:
        signs_e = _non_budget_signs(e)
        is_dom = any(
            o is not e
            and o["departures_addressed"] >= e["departures_addressed"]
            and o["declined_addressed"] >= e["declined_addressed"]
            and o["first_year_cost_usd"] <= e["first_year_cost_usd"]
            and _non_budget_signs(o) <= signs_e
            and (
                (o["departures_addressed"], o["declined_addressed"], -o["first_year_cost_usd"], -len(_non_budget_signs(o)))
                > (e["departures_addressed"], e["declined_addressed"], -e["first_year_cost_usd"], -len(signs_e))
                or (o["departures_addressed"] == e["departures_addressed"]
                    and o["declined_addressed"] == e["declined_addressed"]
                    and o["first_year_cost_usd"] == e["first_year_cost_usd"]
                    and _non_budget_signs(o) == signs_e
                    and (len(o["plan"]), o["signature"]) < (len(e["plan"]), e["signature"]))
            )
            for o in nodes
        )
        key = (e["departures_addressed"], e["declined_addressed"], e["first_year_cost_usd"], signs_e)
        if not is_dom and key not in seen:
            seen.add(key)
            kept.append(e["plan"])
    return kept


def evaluate_org_plan(facts_by_scope: dict[tuple[str, str], dict[str, Any]], scopes: list[tuple[str, str]],
                      plans_tuple: tuple[tuple[tuple[str, str], ...], ...], budget_usd: float | None = None,
                      cohort_cache: dict[tuple[str, str], dict[Any, dict[str, Any]]] | None = None) -> dict[str, Any]:
    """Deterministic multi-cohort critic enforcing shared VP-org ledgers or a pooled budget."""
    per_cohort = [(cohort_cache[s][p] if cohort_cache and p in cohort_cache.get(s, {}) else evaluate(facts_by_scope[s], p))
                  for s, p in zip(scopes, plans_tuple)]
    total_cost = sum(c["first_year_cost_usd"] for c in per_cohort)
    total_dep = sum(c["departures_addressed"] for c in per_cohort)
    total_dec = sum(c["declined_addressed"] for c in per_cohort)
    sign_offs: list[str] = []

    if budget_usd is not None:
        fits = total_cost <= budget_usd
        gap = max(0.0, total_cost - budget_usd)
        if not fits:
            sign_offs.append("VP, above the remaining proactive budget (Section 6.2)")
    else:
        org_spend: dict[str, float] = {}
        org_budget: dict[str, float] = {}
        for (org, _), c in zip(scopes, per_cohort):
            org_spend[org] = org_spend.get(org, 0.0) + c["first_year_cost_usd"]
            org_budget[org] = facts_by_scope[(org, _)]["remaining_budget_usd"]
        gap = sum(max(0.0, org_spend[org] - org_budget[org]) for org in org_spend)
        fits = gap == 0.0
        for org in sorted(org_spend):
            if org_spend[org] > org_budget[org]:
                label = ("VP, above the remaining proactive budget (Section 6.2)"
                         if len(org_spend) == 1 else f"VP ({org}), above the remaining proactive budget (Section 6.2)")
                sign_offs.append(label)

    for c in per_cohort:
        for s in c["sign_offs"]:
            if not s.startswith("VP, above") and s not in sign_offs:
                sign_offs.append(s)

    sig = " || ".join(f"{fam}:{c['signature']}" for (_, fam), c in zip(scopes, per_cohort))
    return {
        "plan": plans_tuple,
        "signature": sig,
        "departures_addressed": total_dep,
        "declined_addressed": total_dec,
        "first_year_cost_usd": total_cost,
        "fits_remaining_budget": fits,
        "budget_gap_usd": gap,
        "sign_offs": sign_offs,
        "lever_count": sum(len(p) for p in plans_tuple),
    }


def _org_order(e: dict[str, Any]) -> tuple:
    return (not e["fits_remaining_budget"], -e["departures_addressed"], -e["declined_addressed"],
            len(e["sign_offs"]), e["first_year_cost_usd"], e["lever_count"], e["signature"])


def _choose_org_options(nodes: list[dict[str, Any]], total_departures: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    front: list[dict[str, Any]] = []
    for e in sorted(nodes, key=_org_order):
        if not any(f["departures_addressed"] >= e["departures_addressed"]
                   and f["declined_addressed"] >= e["declined_addressed"]
                   and f["first_year_cost_usd"] <= e["first_year_cost_usd"]
                   and len(f["sign_offs"]) <= len(e["sign_offs"]) for f in front):
            front.append(e)
    half = math.ceil(POLICY["mismatch_share"] * total_departures)
    picks: list[dict[str, Any]] = []
    rules = [
        ("most coverage inside the remaining budget", lambda e: e["fits_remaining_budget"], _org_order),
        ("most coverage at any cost", lambda e: True,
         lambda e: (-e["departures_addressed"], -e["declined_addressed"], e["first_year_cost_usd"], e["signature"])),
        ("cheapest plan that answers at least half of the departures", lambda e: e["departures_addressed"] >= half,
         lambda e: (e["first_year_cost_usd"], -e["departures_addressed"], e["signature"])),
    ]
    for role, allowed, key in rules:
        pool = [e for e in front if allowed(e) and e["signature"] not in {p["signature"] for p in picks}]
        if pool:
            picks.append({**min(pool, key=key), "role": role})
    for e in sorted(front, key=_org_order):
        if len(picks) >= 3:
            break
        if e["signature"] not in {p["signature"] for p in picks}:
            picks.append({**e, "role": "next best plan"})
    return picks, front


def plan_org_options(scopes: list[tuple[str, str]] = VP_CLOUD_AI_COHORTS, width: int = BEAM_WIDTH,
                     per_cohort_cap: int = MAX_EVALUATIONS, budget_usd: float | None = None,
                     db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    """Two-stage multi-cohort planner: parallel per-cohort beams followed by Pareto composition."""
    facts_by_scope = {s: cohort_facts(*s, db_path) for s in scopes}
    total_dep = sum(facts_by_scope[s]["departures"]["total"] for s in scopes)
    trees = [search(facts_by_scope[s], width=width, max_evaluations=per_cohort_cap) for s in scopes]
    stage1_evals = sum(t["evaluations"] for t in trees)
    stage1_calls = sum(t["model_calls"] for t in trees)
    stage1_rounds = max((len(t["kept_by_depth"]) for t in trees), default=0)

    candidates = [[()] + composable_cohort_front(t["nodes"]) for t in trees]
    combos = [evaluate_org_plan(facts_by_scope, scopes, pt, budget_usd)
              for pt in itertools.product(*candidates) if any(pt)]
    options, pareto = _choose_org_options(combos, total_dep)
    return {
        "scopes": scopes,
        "width": width,
        "stage1_evaluations": stage1_evals,
        "stage2_evaluations": len(combos),
        "evaluations": stage1_evals + len(combos),
        "model_calls": stage1_calls + len(options),
        "rounds": stage1_rounds + (1 if options else 0),
        "candidate_counts": [len(c) for c in candidates],
        "pareto": pareto,
        "options": options,
    }


def flat_org_beam(scopes: list[tuple[str, str]], width: int = BEAM_WIDTH, max_evaluations: int = MAX_EVALUATIONS,
                  budget_usd: float | None = None, db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    """Unfactored single-tree beam across cohorts, used to test whether single-cohort caps fail at scale."""
    facts_by_scope = {s: cohort_facts(*s, db_path) for s in scopes}
    total_dep = sum(facts_by_scope[s]["departures"]["total"] for s in scopes)
    empty = tuple(() for _ in scopes)
    root = evaluate_org_plan(facts_by_scope, scopes, empty, budget_usd)
    frontier, seen, kept, evaluations, model_calls, rounds = [root], {empty}, [], 0, 0, 0

    for _ in range(1, 4 * len(scopes) + 1):
        children = []
        for node in frontier:
            for idx, sc in enumerate(scopes):
                used = {lv for lv, _ in node["plan"][idx]}
                for action in ACTIONS:
                    if action[0] in used:
                        continue
                    new_sub = tuple(sorted(node["plan"][idx] + (action,)))
                    new_pt = node["plan"][:idx] + (new_sub,) + node["plan"][idx + 1:]
                    if new_pt in seen:
                        continue
                    if evaluations >= max_evaluations:
                        break
                    seen.add(new_pt)
                    evaluations += 1
                    if facts_by_scope[sc]["actions"][action]["eligible"] == 0:
                        continue
                    child = evaluate_org_plan(facts_by_scope, scopes, new_pt, budget_usd)
                    if (child["departures_addressed"], child["declined_addressed"]) == (
                            node["departures_addressed"], node["declined_addressed"]):
                        continue
                    children.append(child)
                if evaluations >= max_evaluations:
                    break
            if evaluations >= max_evaluations:
                break
        if not children:
            break
        children.sort(key=_org_order)
        kept += children
        frontier = []
        for child in children:
            if not any(outcome(f) == outcome(child) for f in frontier) and len(frontier) < width:
                frontier.append(child)
        if frontier:
            rounds += 1
            model_calls += len(frontier)

    options, pareto = _choose_org_options(kept, total_dep) if kept else ([], [])
    return {
        "evaluations": evaluations,
        "model_calls": model_calls,
        "rounds": rounds,
        "pareto": pareto,
        "options": options,
    }


def validate_org_scaling(scopes: list[tuple[str, str]] = VP_CLOUD_AI_COHORTS, budget_usd: float | None = None,
                         widths: tuple[int, ...] = (1, 2, 3), flat_caps: tuple[int, ...] = (40, 240),
                         db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    """Benchmark flat and factored beams against exhaustive multi-cohort evaluation."""
    facts_by_scope = {s: cohort_facts(*s, db_path) for s in scopes}
    total_dep = sum(facts_by_scope[s]["departures"]["total"] for s in scopes)
    cohort_cache = {s: {p["plan"]: p for p in every_plan(facts_by_scope[s])} for s in scopes}
    per_cohort_all = [list(cohort_cache[s]) for s in scopes]
    all_plans = [evaluate_org_plan(facts_by_scope, scopes, pt, budget_usd, cohort_cache)
                 for pt in itertools.product(*per_cohort_all)]
    nonempty = [e for e in all_plans if e["departures_addressed"] > 0 or e["declined_addressed"] > 0]
    exh_opts, exh_front = _choose_org_options(nonempty, total_dep)
    exh_opt_outcomes = [(o["role"], outcome(o)) for o in exh_opts]
    exh_front_outcomes = {outcome(e) for e in exh_front}

    flat_runs = {}
    for cap in flat_caps:
        run = flat_org_beam(scopes, width=BEAM_WIDTH, max_evaluations=cap, budget_usd=budget_usd, db_path=db_path)
        flat_runs[cap] = {
            **run,
            "options_match": [(o["role"], outcome(o)) for o in run["options"]] == exh_opt_outcomes,
            "pareto_match": {outcome(e) for e in run["pareto"]} == exh_front_outcomes,
        }

    factored_runs = {}
    for w in widths:
        run = plan_org_options(scopes, width=w, budget_usd=budget_usd, db_path=db_path)
        factored_runs[w] = {
            **run,
            "options_match": [(o["role"], outcome(o)) for o in run["options"]] == exh_opt_outcomes,
            "pareto_match": {outcome(e) for e in run["pareto"]} == exh_front_outcomes,
        }

    return {
        "scopes": scopes,
        "exhaustive_plans": len(all_plans),
        "exhaustive_model_calls": len(all_plans) - 1,
        "exhaustive_pareto_count": len(exh_front),
        "exhaustive_options": exh_opts,
        "flat_by_cap": flat_runs,
        "factored_by_width": factored_runs,
    }


if __name__ == "__main__":
    args = sys.argv[1:]
    print("=== Single-cohort beam validation against all 32 unique plans (162 ordered paths) ===")
    for org, fam in COHORTS:
        res = validate_cohort_beam(org, fam)
        exh = res["exhaustive"]
        print(f"\n{res['scope']}: exhaustive {exh['plans_evaluated']} plans, "
              f"{len(exh['pareto'])} Pareto plans, {exh['model_calls']} model calls")
        for o in exh["options"]:
            print(f"  exhaustive [{o['role']}]: {o['departures_addressed']} dep, "
                  f"{o['declined_addressed']} dec, {_money(o['first_year_cost_usd'])} ({o['signature']})")
        for w, wr in res["by_width"].items():
            print(f"  width={w}: {wr['evaluations']} evals, {wr['model_calls']} model calls ({wr['rounds']} rounds), "
                  f"3_options_match={wr['options_match']}, missed_pareto={len(wr['missed_pareto'])}, "
                  f"budget_sweep_misses={wr['budget_option_misses']}/{wr['budget_thresholds_tested']}")
    if "--org" in args:
        for label, sc in [("VP_CLOUD_AI shared $2,150,000 budget (1,024 plans)", VP_CLOUD_AI_COHORTS),
                          ("All 3 CONVERGENT cohorts per-org budgets (32,768 plans)", COHORTS)]:
            org_res = validate_org_scaling(sc)
            print(f"\n=== {label} ===")
            for o in org_res["exhaustive_options"]:
                print(f"  exhaustive [{o['role']}]: {o['departures_addressed']} dep, "
                      f"{o['declined_addressed']} dec, {_money(o['first_year_cost_usd'])}")
            for cap, fr in org_res["flat_by_cap"].items():
                print(f"  flat width=3 cap={cap}: {fr['evaluations']} evals, {fr['model_calls']} model calls, "
                      f"3_options_match={fr['options_match']}, pareto_match={fr['pareto_match']}")
            for w, kr in org_res["factored_by_width"].items():
                print(f"  factored width={w}: {kr['evaluations']} evals ({kr['stage1_evaluations']}+{kr['stage2_evaluations']}), "
                      f"{kr['model_calls']} model calls, 3_options_match={kr['options_match']}, pareto_match={kr['pareto_match']}")
