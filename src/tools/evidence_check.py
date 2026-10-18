"""Evidence check for conflicting or thin retention signals.

Trigger: run after the roster scan flags a job family and before the agent
retrieves policy or drafts any retention option. The check answers two
questions. Do the roster and the offers log agree that the job family is at
risk? How much data stands behind each signal?

The roster lists every employee, so its counts carry no sampling error. The
offers log holds a handful of events per job family, so every rate or average
taken from it comes with a 95 percent interval. A market indicator counts as
conclusive only when its whole interval sits on one side of the threshold.
Otherwise it only leans one way.

The tool labels the pattern, rates the strength of the evidence and names the
next step. The model explains the result to the partner, and the partner
decides. Thresholds come from docs/policies/compensation_governance_playbook.md
unless THRESHOLDS marks them as design assumptions.

Example:
    assess_retention_evidence("VP_CLOUD_AI", "RESEARCH_SCI") returns the
    pattern CONVERGENT with MODERATE strength. 35 of 116 people face a cliff
    and competing premiums average 29.1 percent, but new-hire acceptance of
    53.8 percent rests on 13 offers, with an interval of 29.1 to 76.8 percent.

Standard library only.
"""

from __future__ import annotations

from contextlib import closing
import math
from pathlib import Path
import sqlite3
import statistics
from typing import Any

from src.tools.deterministic_analytics import DEFAULT_DB_PATH

THRESHOLDS: dict[str, float] = {
    # Playbook Sections 2.2 and 3: a YoY Intended Cashflow drop of 15 percent
    # or more is a cliff.
    "cliff_drop_pct": -15.0,
    # Design assumption: a job family is an internal risk when at least
    # 10 percent of its people face a cliff.
    "cliff_share_pct": 10.0,
    # Playbook Section 2.1: new-hire offer acceptance below 65 percent.
    "acceptance_floor_pct": 65.0,
    # Design assumption: counter-offers use the same 65 percent floor.
    "counter_win_floor_pct": 65.0,
    # Playbook Section 3, Tier 3: a competing premium above 25 percent.
    "competitor_premium_pct": 25.0,
    # Playbook Section 2.1: more than 5 counter-offers in one quarter.
    "max_counters_per_quarter": 5,
    # Design assumptions: smaller samples are reported but never used as
    # evidence.
    "min_events": 5,
    "min_headcount": 20,
}

RISK = "RISK"
LEANS_RISK = "LEANS_RISK"
LEANS_STABLE = "LEANS_STABLE"
STABLE = "STABLE"
INSUFFICIENT = "INSUFFICIENT_DATA"

NEXT_STEPS: dict[str, tuple[str, str]] = {
    "CONVERGENT": (
        "retrieve_policy",
        "Retrieve the governing policy and cost the intervention options.",
    ),
    "INTERNAL_ONLY": (
        "monitor",
        "Propose no broad retention intervention. Send high performers below"
        " the 25th peer percentile to standard refresh planning and re-check"
        " the market indicators when the next quarter of offers data lands.",
    ),
    "MARKET_ONLY": (
        "refer_offers_desk",
        "Refer the job family to the Offers Desk for a band review. Proactive"
        " grants do not close a hiring band gap.",
    ),
    "INCONCLUSIVE": (
        "investigate",
        "Recommend no spend yet. Pool the job family across VP orgs, read the"
        " loss drivers and tell the partner which data would settle the call.",
    ),
    "NO_SIGNAL": (
        "no_action",
        "Take no action. Keep the job family in the monthly scan.",
    ),
    "INSUFFICIENT_DATA": (
        "widen_scope",
        "Widen the scope to the job family across all VP orgs, or report that"
        " the data cannot support a call.",
    ),
}

# Two-sided 95 percent critical values of Student's t by degrees of freedom.
# Above 30 degrees of freedom the normal value 1.96 is used.
_T95 = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
    8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160,
    14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093,
    20: 2.086, 21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060,
    26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042,
}


def _wilson(successes: int, trials: int, z: float = 1.96) -> tuple[float, float]:
    if trials <= 0 or not 0 <= successes <= trials:
        raise ValueError(
            f"need trials > 0 and 0 <= successes <= trials, got {successes} of {trials}"
        )
    p = successes / trials
    denom = 1 + z * z / trials
    centre = (p + z * z / (2 * trials)) / denom
    half = z * math.sqrt(p * (1 - p) / trials + z * z / (4 * trials * trials)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def wilson_interval(successes: int, trials: int) -> tuple[float, float]:
    """Returns the 95 percent Wilson score interval for a rate, in percent."""
    low, high = _wilson(successes, trials)
    return (round(100 * low, 1), round(100 * high, 1))


def mean_interval(values: list[float]) -> tuple[float, float]:
    """Returns the 95 percent Student's t interval for a mean, in the values' unit."""
    if len(values) < 2:
        raise ValueError("need at least 2 values for an interval")
    t = _T95.get(len(values) - 1, 1.96)
    half = t * statistics.stdev(values) / math.sqrt(len(values))
    mean = statistics.fmean(values)
    return (mean - half, mean + half)


def _rate_indicator(
    name: str, successes: int, trials: int, floor_pct: float
) -> dict[str, Any]:
    """Grades a rate where falling below floor_pct means risk."""
    indicator: dict[str, Any] = {
        "indicator": name,
        "source": "offers_log",
        "events": trials,
        "value_pct": round(100 * successes / trials, 1) if trials else None,
        "interval_95_pct": None,
        "threshold": f"below {floor_pct} percent means risk",
    }
    if trials < THRESHOLDS["min_events"]:
        status = INSUFFICIENT
    else:
        low, high = _wilson(successes, trials)
        floor = floor_pct / 100
        indicator["interval_95_pct"] = [round(100 * low, 1), round(100 * high, 1)]
        if high < floor:
            status = RISK
        elif low >= floor:
            status = STABLE
        else:
            status = LEANS_RISK if successes / trials < floor else LEANS_STABLE
    indicator["status"] = status
    indicator["conclusive"] = status in (RISK, STABLE)
    return indicator


def _premium_indicator(premiums: list[float]) -> dict[str, Any]:
    """Grades the average competing premium, where above the ceiling means risk."""
    ceiling = THRESHOLDS["competitor_premium_pct"]
    indicator: dict[str, Any] = {
        "indicator": "competing_premium",
        "source": "offers_log",
        "events": len(premiums),
        "value_pct": round(statistics.fmean(premiums), 1) if premiums else None,
        "interval_95_pct": None,
        "threshold": f"above {ceiling} percent means risk",
    }
    if len(premiums) < THRESHOLDS["min_events"]:
        status = INSUFFICIENT
    else:
        low, high = mean_interval(premiums)
        indicator["interval_95_pct"] = [round(low, 1), round(high, 1)]
        if low > ceiling:
            status = RISK
        elif high <= ceiling:
            status = STABLE
        else:
            status = LEANS_RISK if statistics.fmean(premiums) > ceiling else LEANS_STABLE
    indicator["status"] = status
    indicator["conclusive"] = status in (RISK, STABLE)
    return indicator


def _cliff_indicator(headcount: int, cliff_count: int) -> dict[str, Any]:
    """Grades the share of the job family facing a cliff. The roster is a census."""
    share_floor = THRESHOLDS["cliff_share_pct"]
    indicator: dict[str, Any] = {
        "indicator": "cliff_share",
        "source": "roster",
        "headcount": headcount,
        "cliff_count": cliff_count,
        "value_pct": round(100 * cliff_count / headcount, 1) if headcount else None,
        "threshold": f"{share_floor} percent or more facing a cliff means risk",
    }
    if headcount < THRESHOLDS["min_headcount"]:
        status = INSUFFICIENT
    elif 100 * cliff_count / headcount >= share_floor:
        status = RISK
    else:
        status = STABLE
    indicator["status"] = status
    indicator["conclusive"] = status in (RISK, STABLE)
    return indicator


def classify(internal_status: str, market_statuses: list[str]) -> tuple[str, str]:
    """Returns (pattern, evidence_strength) from the indicator statuses.

    Rules, in order:
    1. Fewer than min_headcount people, or no market indicator with min_events
       events, gives INSUFFICIENT_DATA.
    2. With a cliff signal, more conclusive market risk than conclusive
       stability gives CONVERGENT. No conclusive risk and at least one
       conclusive stable indicator gives INTERNAL_ONLY. Anything else gives
       INCONCLUSIVE.
    3. Without a cliff signal, more conclusive risk than stability gives
       MARKET_ONLY, and anything else gives NO_SIGNAL.
    Only conclusive market indicators count toward the margin. Strength is
    STRONG for a margin of 2 or more, MODERATE for 1 and WEAK otherwise.
    """
    risk = market_statuses.count(RISK)
    stable = market_statuses.count(STABLE)
    usable = len([s for s in market_statuses if s != INSUFFICIENT])
    if internal_status == INSUFFICIENT or usable == 0:
        return "INSUFFICIENT_DATA", "WEAK"
    if internal_status == RISK:
        if risk > stable:
            pattern, margin = "CONVERGENT", risk - stable
        elif risk == 0 and stable >= 1:
            pattern, margin = "INTERNAL_ONLY", stable
        else:
            pattern, margin = "INCONCLUSIVE", 0
    elif risk > stable:
        pattern, margin = "MARKET_ONLY", risk - stable
    else:
        pattern, margin = "NO_SIGNAL", stable - risk
    strength = "STRONG" if margin >= 2 else "MODERATE" if margin == 1 else "WEAK"
    return pattern, strength


def assess_retention_evidence(
    vp_org_code: str | None, job_family: str, db_path: Path = DEFAULT_DB_PATH
) -> dict[str, Any]:
    """Checks whether roster and market signals agree for one job family.

    Inputs: a VP org code, or None to pool the job family across every VP org,
    and a job family code. Output: the pattern, the evidence strength, explicit
    flags, the next step, four graded indicators, context counts for the model
    to weigh and any policy triggers. Policy triggers fire on their own. The
    evidence strength tells the joint review how much weight they carry.
    """
    scope_sql = "job_family = ? AND (? IS NULL OR vp_org_code = ?)"
    params = (job_family, vp_org_code, vp_org_code)
    cliff = THRESHOLDS["cliff_drop_pct"]

    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        roster = dict(
            conn.execute(
                """
                SELECT
                    COUNT(*) AS headcount,
                    COALESCE(SUM(yoy_cashflow_change_26_to_27_pct <= :c), 0) AS cliff_count,
                    COALESCE(SUM(yoy_cashflow_change_26_to_27_pct <= :c
                        AND rating_2025 IN ('rating_4', 'rating_5')), 0) AS high_performer_cliff_count,
                    COALESCE(SUM(yoy_cashflow_change_26_to_27_pct <= :c
                        AND peer_percentile_2027 < 25), 0) AS cliff_below_p25_2027,
                    COALESCE(SUM(yoy_cashflow_change_26_to_27_pct <= :c
                        AND prior_proactive_grant_24m = 1), 0) AS cliff_with_prior_proactive_grant,
                    COALESCE(SUM(yoy_cashflow_change_26_to_27_pct <= :c
                        AND tenure_years < 1.0), 0) AS cliff_tenure_under_1y,
                    COALESCE(SUM(yoy_cashflow_change_26_to_27_pct <= :c
                        AND governance_flag != 'Clean'), 0) AS cliff_with_governance_flag
                FROM org_roster_cashflows
                WHERE job_family = :f AND (:o IS NULL OR vp_org_code = :o)
                """,
                {"c": cliff, "f": job_family, "o": vp_org_code},
            ).fetchone()
        )
        offers = [
            dict(r)
            for r in conn.execute(
                f"""
                SELECT event_type, COUNT(*) AS events,
                       SUM(outcome = 'Accepted_Retained') AS won
                FROM reactive_offers_counters WHERE {scope_sql}
                GROUP BY event_type
                """,
                params,
            )
        ]
        premiums = [
            float(r[0])
            for r in conn.execute(
                f"SELECT competing_offer_premium_pct FROM reactive_offers_counters WHERE {scope_sql}",
                params,
            )
        ]
        counters_by_quarter = {
            r[0]: r[1]
            for r in conn.execute(
                f"""
                SELECT quarter, COUNT(*) FROM reactive_offers_counters
                WHERE {scope_sql} AND event_type = 'Reactive_Counter_Offer'
                GROUP BY quarter ORDER BY quarter
                """,
                params,
            )
        }
        loss_drivers = {
            r[0]: r[1]
            for r in conn.execute(
                f"""
                SELECT primary_loss_driver, COUNT(*) FROM reactive_offers_counters
                WHERE {scope_sql} AND outcome = 'Declined_Lost'
                GROUP BY primary_loss_driver ORDER BY COUNT(*) DESC, primary_loss_driver
                """,
                params,
            )
        }

    by_type = {o["event_type"]: o for o in offers}
    new_hire = by_type.get("New_Hire_Offer", {"events": 0, "won": 0})
    counter = by_type.get("Reactive_Counter_Offer", {"events": 0, "won": 0})

    internal = _cliff_indicator(roster["headcount"], roster["cliff_count"])
    market = [
        _rate_indicator(
            "new_hire_acceptance",
            new_hire["won"],
            new_hire["events"],
            THRESHOLDS["acceptance_floor_pct"],
        ),
        _rate_indicator(
            "counter_offer_win_rate",
            counter["won"],
            counter["events"],
            THRESHOLDS["counter_win_floor_pct"],
        ),
        _premium_indicator(premiums),
    ]
    pattern, strength = classify(internal["status"], [m["status"] for m in market])
    step = NEXT_STEPS[pattern]
    if pattern == "INSUFFICIENT_DATA" and vp_org_code is None:
        step = ("report_data_gap", "Report that the data cannot support a call.")

    policy_triggers = []
    acceptance = market[0]
    if new_hire["events"] and acceptance["value_pct"] < THRESHOLDS["acceptance_floor_pct"]:
        policy_triggers.append(
            f"New-hire acceptance is {acceptance['value_pct']} percent on"
            f" {new_hire['events']} offers, below the"
            f" {THRESHOLDS['acceptance_floor_pct']} percent escalation floor."
        )
    for quarter, count in counters_by_quarter.items():
        if count > THRESHOLDS["max_counters_per_quarter"]:
            policy_triggers.append(
                f"{count} counter-offers in {quarter}, above the limit of"
                f" {THRESHOLDS['max_counters_per_quarter']} per quarter."
            )

    return {
        "scope": {"vp_org_code": vp_org_code or "ALL_ORGS", "job_family": job_family},
        "pattern": pattern,
        "evidence_strength": strength,
        "retention_spend_supported": pattern == "CONVERGENT",
        "uncertainty_disclosure_required": strength != "STRONG"
        or pattern in ("INCONCLUSIVE", "INSUFFICIENT_DATA"),
        "next_step": step[0],
        "next_step_detail": step[1],
        "indicators": [internal, *market],
        "context": {
            "high_performer_cliff_count": roster["high_performer_cliff_count"],
            "cliff_below_p25_2027": roster["cliff_below_p25_2027"],
            "cliff_with_prior_proactive_grant": roster["cliff_with_prior_proactive_grant"],
            "cliff_tenure_under_1y": roster["cliff_tenure_under_1y"],
            "cliff_with_governance_flag": roster["cliff_with_governance_flag"],
            "counters_by_quarter": counters_by_quarter,
            "loss_drivers": loss_drivers,
        },
        "policy_triggers": policy_triggers,
    }
