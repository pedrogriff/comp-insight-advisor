"""Driver fit: match each retention lever to the reasons people give for leaving.

Trigger: run after assess_retention_evidence and before the brief compares
options. The evidence check answers whether to act. This tool answers which
lever addresses the cause, how much of the loss each option covers, and what
each option costs in its first year.

The offers log records one primary loss driver for every lost offer. A lost
counter-offer means an employee left, so its driver is the departure reason.
A declined new-hire offer is hiring evidence. The tool counts the two apart:
retention levers answer departures, and the Offers Desk band review answers
declined offers.

LEVERS, OPTIONS and POLICY mirror Sections 5 and 6 of
docs/policies/compensation_governance_playbook.md, and unit tests check that
the playbook names the same drivers and limits. Code computes every count and
cost. The model explains the trade-offs to the partner, and the partner decides.

Example:
    assess_intervention_fit("VP_CLOUD_AI", "RESEARCH_SCI") finds 4 departures.
    2 cite level, 1 base salary and 1 equity. A retention grant addresses 1 of
    the 4, so default_lever_mismatch is true and Option C adds base
    adjustments and level reviews to the grants. 7 employees qualify for
    both, and joint_pricing counts each of them once.

Standard library only.
"""

from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3
from typing import Any

from src.tools.deterministic_analytics import DEFAULT_DB_PATH, TIER0_RATINGS, simulate_proactive_retention_scenarios
from src.tools.evidence_check import wilson_interval

DEPARTURE_EVENT = "Reactive_Counter_Offer"
HIRING_EVENT = "New_Hire_Offer"
LOST = "Declined_Lost"
DRIVERS = ("Total_Equity_Size", "Cashflow_Year1_Gap", "Base_Salary_Cap", "Level_Up_Offer")
HIGH_PERFORMER = ("rating_4", "rating_5")
# Playbook Section 3, Tier 0: no proactive budget for anyone rated rating_1 or rating_2 (TIER0_RATINGS),
# or for anyone who received a proactive retention grant in the past 24 months.

POLICY: dict[str, float] = {
    # Playbook Sections 2.2 and 3: a cliff is a YoY Intended Cashflow drop of 15 percent or more.
    "cliff_drop_pct": -15.0,
    # Playbook Section 6.2, Pedro's decision of Oct 22, 2026: no base below a 0.80
    # compa-ratio, and an off-cycle adjustment lifts base to a 0.95 compa-ratio at most.
    "compa_floor": 0.80,
    "compa_lift_max": 0.95,
    # Playbook Section 6, design assumptions Pedro confirmed on Oct 22, 2026.
    "mismatch_share": 0.5,
    "min_departures": 5,
    # Playbook Section 6.3, design assumption still to confirm.
    "level_min_tenure_years": 2.0,
}

# The synthetic ladder from data/synthetic/generate_synthetic_data.py. A market reference
# point is the level base times the region multiplier, rounded to $100, and the equity refresh
# guideline follows the same rule. A unit test checks next_level_reference against the data.
LEVEL_BASE_MRP = {"IC1": 145000, "IC2": 185000, "IC3": 230000, "IC4": 285000, "IC5": 350000}
LEVEL_BONUS_PCT = {"IC1": 0.15, "IC2": 0.15, "IC3": 0.20, "IC4": 0.25, "IC5": 0.30}
LEVEL_REFRESH_GUIDELINE = {"IC1": 45000, "IC2": 80000, "IC3": 140000, "IC4": 250000, "IC5": 450000}
REGION_MULTIPLIER = {"US_ZONE_A": 1.15, "US_ZONE_B": 1.10, "US_ZONE_C": 0.95,
                     "UK_ZONE_A": 0.85, "EU_ZONE_A": 0.92, "APAC_ZONE_A": 0.80}
NEXT_LEVEL = {"IC1": "IC2", "IC2": "IC3", "IC3": "IC4", "IC4": "IC5"}


def next_level_reference(level: str, region: str, mrp: float, guideline: float) -> tuple[float, float] | None:
    """Returns the next level's market reference and refresh guideline, or None at the top level.

    Known regions use the ladder's region multiplier. Any other region scales the current
    figures by the ratio of the two levels.
    """
    nxt = NEXT_LEVEL.get(level)
    if nxt is None:
        return None
    if region in REGION_MULTIPLIER:
        mult = REGION_MULTIPLIER[region]
        return float(round(LEVEL_BASE_MRP[nxt] * mult, -2)), float(round(LEVEL_REFRESH_GUIDELINE[nxt] * mult, -2))
    return (mrp * LEVEL_BASE_MRP[nxt] / LEVEL_BASE_MRP[level],
            guideline * LEVEL_REFRESH_GUIDELINE[nxt] / LEVEL_REFRESH_GUIDELINE[level])

LEVERS: dict[str, dict[str, Any]] = {
    "retention_grant": {
        "name": "Proactive retention grant or cliff bridge",
        "addresses": ("Total_Equity_Size", "Cashflow_Year1_Gap"),
        "answers": "departures",
        "owner": "Strategic Compensation Partner",
        "playbook": "Sections 3 and 6.1",
    },
    "base_adjustment": {
        "name": "Off-cycle base adjustment",
        "addresses": ("Base_Salary_Cap",),
        "answers": "departures",
        "owner": "Strategic Compensation Partner",
        "playbook": "Section 6.2",
    },
    "level_review": {
        "name": "Level review that can lead to a promotion",
        "addresses": ("Level_Up_Offer",),
        "answers": "departures",
        "owner": "People manager and calibration committee, with the Strategic Compensation Partner costing it",
        "playbook": "Section 6.3",
    },
    "offer_band_review": {
        "name": "New-hire band and offer review",
        "addresses": DRIVERS,
        "answers": "declined_offers",
        "owner": "Reactive Offers and Counter-Offers Desk",
        "playbook": "Sections 2.1 and 6.4",
    },
}

OPTIONS: dict[str, dict[str, Any]] = {
    "A": {"name": "Offer and counter posture shift", "levers": ("offer_band_review", "retention_grant"),
          "grant_branch": "Branch_A_Offer_Posture_Plus_Top_Ceiling", "adds_on_mismatch": ()},
    "B": {"name": "Targeted proactive cliff bridge", "levers": ("retention_grant",),
          "grant_branch": "Branch_B_Full_Proactive_Cliff_Coverage", "adds_on_mismatch": ()},
    "C": {"name": "Hybrid co-owned plan", "levers": ("retention_grant", "offer_band_review"),
          "grant_branch": "Branch_C_Targeted_High_Performer_Bridge_And_Joint_Offer_Calibration",
          "adds_on_mismatch": ("base_adjustment", "level_review")},
}

ROSTER_COLUMNS = (
    "job_level", "region", "rating_2025", "promoted_last_6m", "tenure_years", "base_salary_usd",
    "market_reference_usd", "compa_ratio", "bonus_target_pct", "equity_refresh_guideline_usd",
    "yoy_cashflow_change_26_to_27_pct", "prior_proactive_grant_24m",
)


def _hundreds(value: float) -> int:
    return int(round(value, -2))


def _driver_counts(conn: sqlite3.Connection, org: str, family: str, event_type: str) -> dict[str, Any]:
    rows = conn.execute(
        "SELECT primary_loss_driver, COUNT(*) FROM reactive_offers_counters"
        " WHERE vp_org_code = ? AND job_family = ? AND event_type = ? AND outcome = ?"
        " GROUP BY primary_loss_driver",
        (org, family, event_type, LOST),
    ).fetchall()
    by_driver = {driver: 0 for driver in DRIVERS}
    unclassified = 0
    for driver, count in rows:
        if driver in by_driver:
            by_driver[driver] = int(count)
        else:
            unclassified += int(count)
    return {"total": sum(by_driver.values()) + unclassified, "by_driver": by_driver, "unclassified": unclassified}


def _base_adjustment(roster: list[dict[str, Any]], cliff: list[dict[str, Any]]) -> dict[str, Any]:
    """Lifts cliff-facing employees outside Tier 0 to the lift ceiling. Never lowers pay.

    The lift is charged to the proactive budget, which Tier 0 withholds, so Tier 0
    employees below the ceiling are counted as held. The 0.80 floor still applies to them.
    """
    lift_to = POLICY["compa_lift_max"]
    candidates, held, base_increase, bonus_increase = 0, 0, 0.0, 0.0
    for row in cliff:
        if row["compa_ratio"] >= lift_to:
            continue
        delta = max(0.0, round(lift_to * row["market_reference_usd"], -2) - row["base_salary_usd"])
        if delta <= 0:
            continue
        if row["rating_2025"] in TIER0_RATINGS or row["prior_proactive_grant_24m"]:
            held += 1
            continue
        candidates += 1
        base_increase += delta
        bonus_increase += delta * row["bonus_target_pct"]
    floor = POLICY["compa_floor"]
    breaches = [r for r in roster if r["compa_ratio"] < floor]
    floor_fix = sum(max(0.0, round(floor * r["market_reference_usd"], -2) - r["base_salary_usd"]) for r in breaches)
    return {
        "candidates": candidates,
        "held_by_tier0": held,
        "annual_base_increase_usd": _hundreds(base_increase),
        "annual_bonus_target_increase_usd": _hundreds(bonus_increase),
        "annual_cost_usd": _hundreds(base_increase) + _hundreds(bonus_increase),
        "rule": (f"Lift cliff-facing employees below a {lift_to:.2f} compa-ratio to {lift_to:.2f}, except "
                 f"Tier 0: rated 1 or 2, or a proactive grant in the past 24 months."),
        "_floor_breaches": len(breaches),
        "_floor_fix": _hundreds(floor_fix),
    }


def _level_review(cliff: list[dict[str, Any]]) -> dict[str, Any]:
    """Costs a promotion to the next level for each eligible cliff-facing high performer."""
    eligible = [
        r for r in cliff
        if r["rating_2025"] in HIGH_PERFORMER and not r["promoted_last_6m"]
        and r["tenure_years"] >= POLICY["level_min_tenure_years"]
    ]
    costed = [r for r in eligible if r["job_level"] in NEXT_LEVEL]
    floor, ceiling = POLICY["compa_floor"], POLICY["compa_lift_max"]
    base_low = base_high = bonus_low = bonus_high = equity = 0.0
    for r in costed:
        nxt = NEXT_LEVEL[r["job_level"]]
        guideline = r["equity_refresh_guideline_usd"]
        next_mrp, next_guideline = next_level_reference(r["job_level"], r["region"], r["market_reference_usd"], guideline)
        base = r["base_salary_usd"]
        low = max(base, round(floor * next_mrp, -2))
        high = max(base, round(ceiling * next_mrp, -2))
        base_low += low - base
        base_high += high - base
        bonus_low += low * LEVEL_BONUS_PCT[nxt] - base * r["bonus_target_pct"]
        bonus_high += high * LEVEL_BONUS_PCT[nxt] - base * r["bonus_target_pct"]
        equity += next_guideline - guideline
    return {
        "candidates": len(eligible),
        "costed": len(costed),
        "at_top_level": len(eligible) - len(costed),
        "annual_base_increase_usd": _hundreds(base_low),
        "annual_base_increase_high_usd": _hundreds(base_high),
        "annual_bonus_target_increase_usd": _hundreds(bonus_low),
        "annual_bonus_target_increase_high_usd": _hundreds(bonus_high),
        "annual_equity_guideline_increase_usd": _hundreds(equity),
        "annual_cost_usd": _hundreds(base_low) + _hundreds(bonus_low) + _hundreds(equity),
        "annual_cost_high_usd": _hundreds(base_high) + _hundreds(bonus_high) + _hundreds(equity),
        "rule": (f"Rated 4 or 5, not promoted in the last 6 months, at least "
                 f"{POLICY['level_min_tenure_years']:g} years of tenure. The estimate moves base to the next "
                 f"level's {floor:.2f} compa-ratio, the high case to {ceiling:.2f}."),
    }


def joint_pricing(cliff: list[dict[str, Any]]) -> dict[str, Any]:
    """Prices a base lift and a promotion for the same employee once.

    On the synthetic ladder the next level's market reference is at least 1.22 times this
    level's, so a promotion's low case, the next level's 0.80 compa-ratio, already lands above
    this level's 0.95 lift ceiling. A plan with both levers pays the promotion and drops that
    employee's lift. The credit is what the lift would have cost those employees, base and bonus.
    """
    both = [r for r in cliff if _base_adjustment([r], [r])["candidates"] and _level_review([r])["costed"]]
    return {
        "employees": len(both),
        "credit_usd": float(_base_adjustment(both, both)["annual_cost_usd"]) if both else 0.0,
        "rule": ("An employee costed for a base lift and a promotion counts once: the plan pays the "
                 "promotion and drops the lift."),
    }


def _covered(levers: list[str], departures: dict[str, Any], declined: dict[str, Any]) -> tuple[int, int]:
    dep_drivers = {d for key in levers if LEVERS[key]["answers"] == "departures" for d in LEVERS[key]["addresses"]}
    dec_drivers = {d for key in levers if LEVERS[key]["answers"] == "declined_offers" for d in LEVERS[key]["addresses"]}
    return (sum(departures["by_driver"][d] for d in dep_drivers),
            sum(declined["by_driver"][d] for d in dec_drivers))


def assess_intervention_fit(vp_org_code: str, job_family: str, db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    """Separates loss drivers, matches levers to them, and costs the three brief options."""
    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        departures = _driver_counts(conn, vp_org_code, job_family, DEPARTURE_EVENT)
        declined = _driver_counts(conn, vp_org_code, job_family, HIRING_EVENT)
        roster = [dict(r) for r in conn.execute(
            f"SELECT {', '.join(ROSTER_COLUMNS)} FROM org_roster_cashflows WHERE vp_org_code = ? AND job_family = ?",
            (vp_org_code, job_family),
        )]
        budget = conn.execute(
            "SELECT proactive_remaining_usd FROM department_budgets WHERE vp_org_code = ?", (vp_org_code,)
        ).fetchone()
    remaining = float(budget[0]) if budget else 0.0
    cliff = [r for r in roster if r["yoy_cashflow_change_26_to_27_pct"] <= POLICY["cliff_drop_pct"]]

    grants = simulate_proactive_retention_scenarios(vp_org_code, job_family, db_path)
    branch_cost = {b["branch_id"]: float(b["estimated_proactive_cost_usd"]) for b in grants["strategic_branches"]}
    base = _base_adjustment(roster, cliff)
    level = _level_review(cliff)
    joint = joint_pricing(cliff)
    costs = {
        "retention_grant": {"one_time_grant_cost_usd": branch_cost["Branch_B_Full_Proactive_Cliff_Coverage"],
                            "candidates_by_tier": grants["eligible_cliff_candidates_by_tier"],
                            "held_by_tier0": grants["held_by_tier0"]},
        "base_adjustment": {k: v for k, v in base.items() if not k.startswith("_")},
        "level_review": level,
        "offer_band_review": {"note": "The Offers Desk owns new-hire bands. No proactive budget cost."},
    }

    levers = []
    for key, spec in LEVERS.items():
        dep, dec = _covered([key], departures, declined)
        levers.append({"lever": key, "name": spec["name"], "addresses": list(spec["addresses"]),
                       "answers": spec["answers"], "owner": spec["owner"], "playbook": spec["playbook"],
                       "departures_addressed": dep, "declined_offers_addressed": dec, **costs[key]})

    n_dep = departures["total"]
    grant_covers = levers[0]["departures_addressed"]
    mismatch = n_dep > 0 and grant_covers < POLICY["mismatch_share"] * n_dep
    retention = [item for item in levers if item["answers"] == "departures"]
    top = max(retention, key=lambda item: item["departures_addressed"])
    leading = top["lever"] if n_dep and top["departures_addressed"] else None

    options = []
    for key, spec in OPTIONS.items():
        chosen = list(spec["levers"]) + (list(spec["adds_on_mismatch"]) if mismatch else [])
        dep, dec = _covered(chosen, departures, declined)
        credit = joint["credit_usd"] if {"base_adjustment", "level_review"} <= set(chosen) else 0.0
        cost = branch_cost[spec["grant_branch"]]
        cost += base["annual_cost_usd"] if "base_adjustment" in chosen else 0
        cost += level["annual_cost_usd"] if "level_review" in chosen else 0
        cost -= credit
        options.append({
            "option": key, "name": spec["name"], "levers": chosen,
            "departures_addressed": dep, "departures": n_dep,
            "declined_offers_addressed": dec, "declined_offers": declined["total"],
            "first_year_cost_usd": cost, "joint_pricing_credit_usd": credit, "remaining_budget_usd": remaining,
            "fits_remaining_budget": cost <= remaining, "budget_gap_usd": max(0.0, cost - remaining),
            "partial_fit": n_dep > 0 and dep < POLICY["mismatch_share"] * n_dep,
        })

    thin = n_dep < POLICY["min_departures"]
    if not n_dep:
        settle = "No departures after a counter-offer are on record, so the reasons for leaving are unknown."
    elif thin:
        drivers = " and ".join(d for d in LEVERS[leading]["addresses"]) if leading else "any driver"
        settle = (f"{n_dep} departures are too few to rank the reasons with confidence. Stay interviews with the "
                  f"{len(cliff)} cliff-facing employees, or next quarter's departures, would show whether "
                  f"{drivers} leads.")
    else:
        settle = f"{n_dep} departures give a usable read. Recheck the drivers after next quarter's departures."

    return {
        "scope": {"vp_org_code": vp_org_code, "job_family": job_family},
        "departures": departures,
        "declined_offers": declined,
        "levers": levers,
        "leading_lever": leading,
        "leading_share_interval_95_pct": (
            list(wilson_interval(top["departures_addressed"], n_dep)) if leading else None),
        "flags": {
            "default_lever_mismatch": mismatch,
            "thin_driver_evidence": thin,
            "needs_calibration": departures["by_driver"]["Level_Up_Offer"] > 0,
            "compa_floor_breach": base["_floor_breaches"] > 0,
        },
        "options": options,
        "joint_pricing": joint,
        "governance": {
            "compa_floor_breaches": base["_floor_breaches"],
            "compa_floor_fix_usd": base["_floor_fix"],
            "rule": f"No base below a {POLICY['compa_floor']:.2f} compa-ratio, in any option.",
        },
        "settle_it": settle,
        "policy": dict(POLICY),
    }
