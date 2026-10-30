"""Tree-of-Thought planner for the brief's three options (checkpoint 4.1).

Where it runs. After the evidence check returns CONVERGENT and the driver-fit tool has counted
departures and declined offers, the brief must offer three costed options (playbook Section 5).
A linear chain commits to the default lever, a retention grant, because the evidence says "cliff":
the template options A and B are both grant-led, and for research scientists the best template
inside the budget answers 1 of 4 departures. The planner searches lever plans instead.

The tree:
- A thought is one decision that extends a plan, such as "lift base to the 0.95 ceiling for
  the eligible employees". A node is the plan so far, with the facts the tools compute for it:
  departures and declined offers addressed, first-year cost, budget fit and sign-offs.
- Depth is the number of levers decided, at most 4: grant sizing, base lift, level review and the
  new-hire band review. The root has 6 children, because grants come in three sizings.
- Search is a beam of width 3. Every child gets the code checks below, the 3 best go on, and the
  search stops at depth 4, when no child adds coverage, or after MAX_EVALUATIONS nodes.

The critic is code, so no figure comes from a model:
- Eligibility. A lever with no eligible employee addresses nothing, however its drivers read.
- No-op. A child that adds no departure or declined offer is pruned.
- Duplicates. Two paths to the same plan are evaluated once, so two options can't be one plan.
- Joint pricing. A base lift and a promotion for the same employee count once. The promotion
  moves base past the lift ceiling, so the plan pays the promotion and drops that employee's lift.
- Ranking: inside the budget first, then departures, declined offers, fewer sign-offs, lower cost.

The decision maker offers three distinct plans that no other plan beats on coverage, cost and
sign-offs at once: the most coverage inside the remaining budget, the most coverage at any cost,
and the cheapest plan that answers at least half of the departures.

From the repo root:
    python3 -m src.planning.tot_planner VP_CLOUD_AI RESEARCH_SCI
    python3 -m src.planning.tot_planner --compare
"""

from __future__ import annotations

from contextlib import closing
import itertools
import math
from pathlib import Path
import sqlite3
import sys
from typing import Any

from src.tools.deterministic_analytics import DEFAULT_DB_PATH, simulate_proactive_retention_scenarios
from src.tools.intervention_fit import (DEPARTURE_EVENT, HIRING_EVENT, LEVERS, POLICY, ROSTER_COLUMNS,
                                        _base_adjustment, _driver_counts, _level_review, assess_intervention_fit,
                                        joint_pricing)

# Grant sizing: (branch in simulate_proactive_retention_scenarios, tiers it funds). Top ceiling funds
# Tier 3 and half of Tier 2, as template Option A does.
GRANT_SIZINGS = {
    "top_ceiling": ("Branch_A_Offer_Posture_Plus_Top_Ceiling", ("Tier_3", "Tier_2")),
    "tier2_and_3": ("Branch_C_Targeted_High_Performer_Bridge_And_Joint_Offer_Calibration", ("Tier_3", "Tier_2")),
    "all_tiers": ("Branch_B_Full_Proactive_Cliff_Coverage", ("Tier_3", "Tier_2", "Tier_1")),
}
ACTIONS = ([("retention_grant", sizing) for sizing in GRANT_SIZINGS]
           + [("base_adjustment", "lift_to_0.95"), ("level_review", "promotion_low_case"),
              ("offer_band_review", "offers_desk")])
BEAM_WIDTH, MAX_DEPTH, MAX_EVALUATIONS = 3, 4, 40
COHORTS = [("VP_CLOUD_AI", "RESEARCH_SCI"), ("VP_CLOUD_AI", "AI_ML_ENG"), ("VP_SEC_INTEL", "CYBER_SEC_ENG")]


def cohort_facts(vp_org_code: str, job_family: str, db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    """Everything the critic needs for one cohort, from the same rules as assess_intervention_fit."""
    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        departures = _driver_counts(conn, vp_org_code, job_family, DEPARTURE_EVENT)
        declined = _driver_counts(conn, vp_org_code, job_family, HIRING_EVENT)
        roster = [dict(r) for r in conn.execute(
            f"SELECT employee_id, {', '.join(ROSTER_COLUMNS)} FROM org_roster_cashflows"
            " WHERE vp_org_code = ? AND job_family = ?", (vp_org_code, job_family))]
        budget = conn.execute("SELECT proactive_remaining_usd FROM department_budgets WHERE vp_org_code = ?",
                              (vp_org_code,)).fetchone()
    cliff = [r for r in roster if r["yoy_cashflow_change_26_to_27_pct"] <= POLICY["cliff_drop_pct"]]
    grants = simulate_proactive_retention_scenarios(vp_org_code, job_family, db_path)
    tiers = grants["eligible_cliff_candidates_by_tier"]
    branch_cost = {b["branch_id"]: float(b["estimated_proactive_cost_usd"]) for b in grants["strategic_branches"]}
    base, level = _base_adjustment(roster, cliff), _level_review(cliff)
    # The same rule as Option C: a base lift and a promotion for one employee count once.
    joint = joint_pricing(cliff)
    actions: dict[tuple[str, str], dict[str, float]] = {}
    for lever, sizing in ACTIONS:
        if lever == "retention_grant":
            branch, funded = GRANT_SIZINGS[sizing]
            eligible, cost = sum(tiers[t] for t in funded), branch_cost[branch]
        elif lever == "base_adjustment":
            eligible, cost = base["candidates"], base["annual_cost_usd"]
        elif lever == "level_review":
            eligible, cost = level["costed"], level["annual_cost_usd"]
        else:
            eligible, cost = declined["total"], 0.0
        actions[(lever, sizing)] = {"eligible": eligible, "cost_usd": float(cost)}
    return {"scope": {"vp_org_code": vp_org_code, "job_family": job_family}, "departures": departures,
            "declined": declined, "remaining_budget_usd": float(budget[0]) if budget else 0.0, "tiers": tiers,
            "actions": actions, "lift_and_promotion": joint["employees"],
            "joint_pricing_credit_usd": joint["credit_usd"]}


def evaluate(facts: dict[str, Any], plan: tuple[tuple[str, str], ...]) -> dict[str, Any]:
    """The critic's facts for one plan. Pure code: counts, costs, budget fit and sign-offs."""
    live = [a for a in plan if facts["actions"][a]["eligible"] > 0]
    dep = {d for lv, _ in live if LEVERS[lv]["answers"] == "departures" for d in LEVERS[lv]["addresses"]}
    dec = {d for lv, _ in live if LEVERS[lv]["answers"] == "declined_offers" for d in LEVERS[lv]["addresses"]}
    levers = {lv for lv, _ in plan}
    credit = facts["joint_pricing_credit_usd"] if {"base_adjustment", "level_review"} <= levers else 0.0
    cost = sum(facts["actions"][a]["cost_usd"] for a in plan) - credit
    remaining = facts["remaining_budget_usd"]
    sign_offs = []
    if cost > remaining:
        sign_offs.append("VP, above the remaining proactive budget (Section 6.2)")
    if "retention_grant" in levers and facts["tiers"]["Tier_3"] > 0:
        sign_offs.append("VP and Head of Compensation, Tier 3 grants (Section 3)")
    if "level_review" in levers:
        sign_offs.append("Calibration committee, level decisions (Section 6.3)")
    return {"plan": plan, "signature": " + ".join(f"{lv}:{sz}" for lv, sz in plan) or "no action",
            "departures_addressed": sum(facts["departures"]["by_driver"][d] for d in dep),
            "declined_addressed": sum(facts["declined"]["by_driver"][d] for d in dec),
            "first_year_cost_usd": cost, "joint_pricing_credit_usd": credit,
            "fits_remaining_budget": cost <= remaining, "budget_gap_usd": max(0.0, cost - remaining),
            "sign_offs": sign_offs}


def order(e: dict[str, Any]) -> tuple:
    """Best first: inside the budget, departures, declined offers, fewer sign-offs, lower cost, fewer levers."""
    return (not e["fits_remaining_budget"], -e["departures_addressed"], -e["declined_addressed"],
            len(e["sign_offs"]), e["first_year_cost_usd"], len(e["plan"]), e["signature"])


def dominated(e: dict[str, Any], others: list[dict[str, Any]]) -> bool:
    def no_worse(o):
        return (o["departures_addressed"] >= e["departures_addressed"] and o["declined_addressed"] >= e["declined_addressed"]
                and o["first_year_cost_usd"] <= e["first_year_cost_usd"] and len(o["sign_offs"]) <= len(e["sign_offs"]))
    return any(o is not e and no_worse(o) and order(o) < order(e) for o in others)


def outcome(e: dict[str, Any]) -> tuple:
    return (e["departures_addressed"], e["declined_addressed"], e["first_year_cost_usd"], tuple(e["sign_offs"]))


def search(facts: dict[str, Any], width: int = BEAM_WIDTH, max_evaluations: int = MAX_EVALUATIONS,
           start: tuple[str, str] | None = None) -> dict[str, Any]:
    """Beam search over lever plans. Returns every evaluated node and every pruning decision.

    `start` forces the first decision, which models a linear chain that commits to one lever first.
    """
    root = {**evaluate(facts, ()), "depth": 0, "parent": None}
    frontier, seen, kept, pruned, evaluations = [root], {()}, [], [], 0
    for depth in range(1, MAX_DEPTH + 1):
        children = []
        for node in frontier:
            used = {lv for lv, _ in node["plan"]}
            for action in ACTIONS:
                if action[0] in used or (depth == 1 and start is not None and action != start):
                    continue
                plan = tuple(sorted(node["plan"] + (action,)))
                if plan in seen:
                    pruned.append({"plan": plan, "depth": depth, "reason": "duplicate: another path reached this plan"})
                    continue
                if evaluations >= max_evaluations:
                    pruned.append({"plan": plan, "depth": depth, "reason": "evaluation budget spent"})
                    continue
                seen.add(plan)
                evaluations += 1
                child = {**evaluate(facts, plan), "depth": depth, "parent": node["signature"]}
                if facts["actions"][action]["eligible"] == 0:
                    pruned.append({"plan": plan, "depth": depth, "reason": f"no employee is eligible for {action[0]}"})
                elif (child["departures_addressed"], child["declined_addressed"]) == (
                        node["departures_addressed"], node["declined_addressed"]):
                    pruned.append({"plan": plan, "depth": depth, "reason": "adds no departure or declined offer"})
                else:
                    children.append(child)
        if not children:
            break
        children.sort(key=order)
        kept += children
        frontier = []
        for child in children:
            twin = next((f for f in frontier if outcome(f) == outcome(child)), None)
            if twin is not None:
                # Two sizings that fund the same people make the same plan. Keep one in the beam.
                pruned.append({"plan": child["plan"], "depth": depth,
                               "reason": f"same coverage, cost and sign-offs as {twin['signature']}"})
            elif len(frontier) < width:
                frontier.append(child)
    return {"facts": facts, "nodes": kept, "pruned": pruned, "evaluations": evaluations, "width": width}


def choose_options(tree: dict[str, Any]) -> list[dict[str, Any]]:
    """The decision maker: three distinct plans from the set no other plan dominates."""
    nodes = tree["nodes"]
    front = [e for e in nodes if not dominated(e, nodes)]
    half = math.ceil(POLICY["mismatch_share"] * tree["facts"]["departures"]["total"])
    picks: list[dict[str, Any]] = []
    rules = [
        ("most coverage inside the remaining budget", lambda e: e["fits_remaining_budget"], order),
        ("most coverage at any cost", lambda e: True,
         lambda e: (-e["departures_addressed"], -e["declined_addressed"], e["first_year_cost_usd"], e["signature"])),
        ("cheapest plan that answers at least half of the departures", lambda e: e["departures_addressed"] >= half,
         lambda e: (e["first_year_cost_usd"], -e["departures_addressed"], e["signature"])),
    ]
    for role, allowed, key in rules:
        pool = [e for e in front if allowed(e) and e["signature"] not in {p["signature"] for p in picks}]
        if pool:
            picks.append({**min(pool, key=key), "role": role})
    for e in sorted(front, key=order):
        if len(picks) >= 3:
            break
        if e["signature"] not in {p["signature"] for p in picks}:
            picks.append({**e, "role": "next best plan"})
    return picks


def plan_options(vp_org_code: str, job_family: str, width: int = BEAM_WIDTH, db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    tree = search(cohort_facts(vp_org_code, job_family, db_path), width)
    return {**tree, "options": choose_options(tree)}


def every_plan(facts: dict[str, Any]) -> list[dict[str, Any]]:
    """All 32 plans for one cohort: no grant or one of three sizings, times base, level and band on or off."""
    grant = [()] + [(a,) for a in ACTIONS[:3]]
    rest = [[(), (a,)] for a in ACTIONS[3:]]
    return [evaluate(facts, tuple(sorted(g + b + l + o))) for g, b, l, o in itertools.product(grant, *rest)]


def compare(cohorts: list[tuple[str, str]] = COHORTS, db_path: Path = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    """Template options against a greedy chain (beam width 1), the beam and the full tree."""
    rows = []
    for org, family in cohorts:
        facts = cohort_facts(org, family, db_path)
        fit = assess_intervention_fit(org, family, db_path)
        inside = [o for o in fit["options"] if o["fits_remaining_budget"]]
        template = min(inside, key=lambda o: (-o["departures_addressed"], o["first_year_cost_usd"])) if inside else None
        costs = [(o["departures_addressed"], o["first_year_cost_usd"]) for o in fit["options"]]
        chain = search(facts, width=1, start=("retention_grant", "top_ceiling"))
        greedy, beam = search(facts, width=1), search(facts)
        full = every_plan(facts)

        def best(nodes):
            pool = [e for e in nodes if e["fits_remaining_budget"]]
            return min(pool, key=order) if pool else None

        rows.append({"scope": f"{org} {family}", "departures": facts["departures"]["total"],
                     "remaining_budget_usd": facts["remaining_budget_usd"],
                     "template": {"option": template["option"], "departures_addressed": template["departures_addressed"],
                                  "first_year_cost_usd": template["first_year_cost_usd"]} if template else None,
                     "template_repeats": len(costs) - len(set(costs)),
                     "grant_first": best(chain["nodes"]), "grant_first_evaluations": chain["evaluations"],
                     "greedy": best(greedy["nodes"]), "greedy_evaluations": greedy["evaluations"],
                     "beam": best(beam["nodes"]), "beam_evaluations": beam["evaluations"],
                     "full": best(full), "full_plans": len(full), "options": choose_options(beam)})
    return rows


def template_audit(db_path: Path = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    """For every cohort with departures: does a template option claim departures at $0, and does the cohort pass the evidence check?"""
    from src.tools.evidence_check import assess_retention_evidence  # here, so the planner imports stay light
    with closing(sqlite3.connect(db_path)) as conn:
        pairs = conn.execute("SELECT DISTINCT vp_org_code, job_family FROM reactive_offers_counters"
                             " WHERE event_type = ? AND outcome = 'Declined_Lost' ORDER BY 1, 2", (DEPARTURE_EVENT,)).fetchall()
    rows = []
    for org, family in pairs:
        options = assess_intervention_fit(org, family, db_path)["options"]
        rows.append({"scope": f"{org} {family}", "pattern": assess_retention_evidence(org, family)["pattern"],
                     "free_claims": sum(1 for o in options if o["first_year_cost_usd"] == 0 and o["departures_addressed"] > 0)})
    return rows


def _money(x: float) -> str:
    return f"${x:,.0f}"


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--compare" in args:
        for r in compare():
            t = r["template"]
            print(f"{r['scope']}: {r['departures']} departures, {_money(r['remaining_budget_usd'])} left")
            print(f"  best template inside budget: Option {t['option']}, {t['departures_addressed']} departures, "
                  f"{_money(t['first_year_cost_usd'])}; templates with the same coverage and cost: {r['template_repeats']}")
            for name in ("grant_first", "greedy", "beam", "full"):
                e = r[name]
                n = r[f"{name}_evaluations"] if name != "full" else r["full_plans"]
                print(f"  {name:<11} {e['departures_addressed']} departures, {_money(e['first_year_cost_usd'])}, "
                      f"{n} plans evaluated: {e['signature']}")
    else:
        org, family = (args[:2] if len(args) >= 2 else COHORTS[0])
        result = plan_options(org, family)
        f = result["facts"]
        print(f"{org} {family}: {f['departures']['total']} departures, {f['declined']['total']} declined offers, "
              f"{_money(f['remaining_budget_usd'])} left, {result['evaluations']} plans evaluated")
        for node in result["nodes"]:
            print(f"  depth {node['depth']}: {node['signature']}: {node['departures_addressed']} departures, "
                  f"{node['declined_addressed']} declined, {_money(node['first_year_cost_usd'])}")
        for p in result["pruned"]:
            print(f"  pruned at depth {p['depth']}: {' + '.join(f'{a}:{b}' for a, b in p['plan'])}: {p['reason']}")
        for o in result["options"]:
            print(f"OPTION ({o['role']}): {o['signature']}: {o['departures_addressed']} of {f['departures']['total']} "
                  f"departures, {o['declined_addressed']} of {f['declined']['total']} declined, "
                  f"{_money(o['first_year_cost_usd'])}, sign-offs: {'; '.join(o['sign_offs']) or 'none'}")
