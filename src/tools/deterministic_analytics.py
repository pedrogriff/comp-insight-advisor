"""Deterministic compensation and offer analytics tools for the Insight Advisor.

Designed so smaller or Flash-tier LLMs never perform spreadsheet math in token
space. Every function queries the synthetic SQLite database and returns a
compact, pre-verified JSON-serializable dictionary with explicit risk flags.
"""

from pathlib import Path
import sqlite3
from typing import Any

DEFAULT_DB_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "data"
    / "synthetic"
    / "comp_insight_advisor.db"
)


def analyze_org_cliff_and_equity_health(
    vp_org_code: str, db_path: Path = DEFAULT_DB_PATH
) -> dict[str, Any]:
    """Computes 2027 cashflow cliff cohorts, peer percentiles, and governance flags."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Overall org summary
        cur.execute(
            """
            SELECT
                COUNT(*) AS total_headcount,
                ROUND(AVG(compa_ratio), 3) AS avg_compa_ratio,
                SUM(CASE WHEN yoy_cashflow_change_26_to_27_pct <= -15.0 THEN 1 ELSE 0 END) AS cliff_count_gt_15pct,
                SUM(CASE WHEN yoy_cashflow_change_26_to_27_pct <= -15.0
                          AND rating_2025 IN ('rating_4', 'rating_5')
                    THEN 1 ELSE 0 END) AS high_performer_cliff_count,
                SUM(CASE WHEN governance_flag LIKE '%Manager Inversion%' THEN 1 ELSE 0 END) AS manager_inversion_count,
                SUM(CASE WHEN governance_flag LIKE '%Stale pre-promotion%' THEN 1 ELSE 0 END) AS stale_promo_band_count
            FROM org_roster_cashflows
            WHERE vp_org_code = ?
            """,
            (vp_org_code,),
        )
        summary = dict(cur.fetchone())

        # Breakdown by job family
        cur.execute(
            """
            SELECT
                job_family,
                COUNT(*) AS headcount,
                ROUND(AVG(compa_ratio), 3) AS avg_compa_ratio,
                ROUND(AVG(yoy_cashflow_change_26_to_27_pct), 1) AS avg_yoy_cashflow_change_pct,
                SUM(CASE WHEN yoy_cashflow_change_26_to_27_pct <= -15.0 THEN 1 ELSE 0 END) AS cliff_headcount,
                ROUND(AVG(peer_percentile_2027), 1) AS avg_2027_peer_percentile
            FROM org_roster_cashflows
            WHERE vp_org_code = ?
            GROUP BY job_family
            ORDER BY cliff_headcount DESC
            """,
            (vp_org_code,),
        )
        family_breakdown = [dict(r) for r in cur.fetchall()]

        # Specific governance anomalies (inversions and stale promo bands)
        cur.execute(
            """
            SELECT employee_id, job_family, job_level, manager_id,
                   intended_cashflow_2026_usd, intended_cashflow_2027_usd,
                   governance_flag
            FROM org_roster_cashflows
            WHERE vp_org_code = ? AND governance_flag != 'Clean'
            LIMIT 15
            """,
            (vp_org_code,),
        )
        governance_alerts = [dict(r) for r in cur.fetchall()]

        # Budget status
        cur.execute(
            """
            SELECT * FROM department_budgets WHERE vp_org_code = ?
            """,
            (vp_org_code,),
        )
        budget_row = cur.fetchone()
        budget_status = dict(budget_row) if budget_row else {}

    return {
        "vp_org_code": vp_org_code,
        "org_summary": summary,
        "job_family_breakdown": family_breakdown,
        "governance_alerts": governance_alerts,
        "budget_status": budget_status,
    }


def analyze_reactive_offers_and_counters(
    vp_org_code: str, db_path: Path = DEFAULT_DB_PATH
) -> dict[str, Any]:
    """Analyzes new-hire offer acceptance rates, counter-offers, and competitor premiums."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        cur.execute(
            """
            SELECT
                job_family,
                event_type,
                COUNT(*) AS total_events,
                SUM(CASE WHEN outcome = 'Accepted_Retained' THEN 1 ELSE 0 END) AS won_count,
                ROUND(100.0 * SUM(CASE WHEN outcome = 'Accepted_Retained' THEN 1 ELSE 0 END) / COUNT(*), 1) AS win_rate_pct,
                ROUND(AVG(competing_offer_premium_pct), 1) AS avg_competing_premium_pct,
                SUM(counter_offer_grant_usd) AS total_counter_grant_spend_usd
            FROM reactive_offers_counters
            WHERE vp_org_code = ?
            GROUP BY job_family, event_type
            ORDER BY win_rate_pct ASC
            """,
            (vp_org_code,),
        )
        by_family_and_type = [dict(r) for r in cur.fetchall()]

        cur.execute(
            """
            SELECT
                competing_employer,
                COUNT(*) AS poached_or_competed_cases,
                ROUND(AVG(competing_offer_premium_pct), 1) AS avg_premium_pct,
                SUM(CASE WHEN outcome = 'Declined_Lost' THEN 1 ELSE 0 END) AS losses_to_competitor
            FROM reactive_offers_counters
            WHERE vp_org_code = ?
            GROUP BY competing_employer
            ORDER BY losses_to_competitor DESC
            """,
            (vp_org_code,),
        )
        competitor_pressure = [dict(r) for r in cur.fetchall()]

    # Flag policy escalation triggers (accept rate < 65% or > 5 counters)
    policy_escalations = []
    for row in by_family_and_type:
        if row["event_type"] == "New_Hire_Offer" and row["win_rate_pct"] < 65.0:
            policy_escalations.append(
                f"{row['job_family']} New-Hire Offer win rate is {row['win_rate_pct']}% (<65% policy threshold)"
            )
        if row["event_type"] == "Reactive_Counter_Offer" and row["total_events"] > 5:
            policy_escalations.append(
                f"{row['job_family']} experienced {row['total_events']} reactive counter-offers (>5 threshold)"
            )

    return {
        "vp_org_code": vp_org_code,
        "offer_and_counter_breakdown": by_family_and_type,
        "competitor_pressure": competitor_pressure,
        "policy_escalation_triggers": policy_escalations,
    }


def simulate_proactive_retention_scenarios(
    vp_org_code: str, job_family: str | None = None, db_path: Path = DEFAULT_DB_PATH
) -> dict[str, Any]:
    """Evaluates 3 Tree-of-Thought intervention branches against the 4-Tier Sizing Rubric."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        query = """
            SELECT employee_id, job_family, job_level, rating_2025,
                   critical_ai_talent_tier, equity_refresh_guideline_usd,
                   intended_cashflow_2026_usd, intended_cashflow_2027_usd,
                   yoy_cashflow_change_26_to_27_pct, prior_proactive_grant_24m
            FROM org_roster_cashflows
            WHERE vp_org_code = ?
              AND yoy_cashflow_change_26_to_27_pct <= -15.0
              AND prior_proactive_grant_24m = 0
        """
        params: list[Any] = [vp_org_code]
        if job_family:
            query += " AND job_family = ?"
            params.append(job_family)

        cur.execute(query, params)
        candidates = [dict(r) for r in cur.fetchall()]

        cur.execute(
            "SELECT proactive_remaining_usd FROM department_budgets WHERE vp_org_code = ?",
            (vp_org_code,),
        )
        budget_row = cur.fetchone()
        remaining_budget = float(budget_row["proactive_remaining_usd"]) if budget_row else 0.0

    # Score candidates into Tiers 1, 2, and 3
    tier1_cost, tier2_cost, tier3_cost = 0.0, 0.0, 0.0
    tier_counts = {"Tier_1": 0, "Tier_2": 0, "Tier_3": 0}

    for c in candidates:
        guideline = float(c["equity_refresh_guideline_usd"])
        rating = c["rating_2025"]
        if rating == "rating_5":
            tier_counts["Tier_3"] += 1
            tier3_cost += round(guideline * 1.60, -3)
        elif rating == "rating_4" or c["critical_ai_talent_tier"] in ("Tier_1", "Tier_2"):
            tier_counts["Tier_2"] += 1
            tier2_cost += round(guideline * 1.15, -3)
        elif rating == "rating_3":
            tier_counts["Tier_1"] += 1
            tier1_cost += round(guideline * 0.65, -3)

    branch_a_cost = round(tier3_cost + tier2_cost * 0.5, -3)
    branch_b_cost = round(tier1_cost + tier2_cost + tier3_cost, -3)
    branch_c_cost = round(tier2_cost + tier3_cost, -3)

    return {
        "vp_org_code": vp_org_code,
        "job_family_filter": job_family or "ALL",
        "remaining_proactive_budget_usd": remaining_budget,
        "eligible_cliff_candidates_by_tier": tier_counts,
        "strategic_branches": [
            {
                "branch_id": "Branch_A_Offer_Posture_Plus_Top_Ceiling",
                "description": "Shift new-hire offer bands upward with the Offers Desk while funding only Tier 3 Transformative and 50% of Tier 2 cliff bridges.",
                "estimated_proactive_cost_usd": branch_a_cost,
                "fits_remaining_budget": branch_a_cost <= remaining_budget,
                "budget_delta_usd": remaining_budget - branch_a_cost,
                "tradeoff_note": "Preserves proactive budget but leaves Tier 1 and half of Tier 2 cliff cohorts exposed to external poaching.",
            },
            {
                "branch_id": "Branch_B_Full_Proactive_Cliff_Coverage",
                "description": "Fund all Tier 1, Tier 2, and Tier 3 cliff candidates across the cohort.",
                "estimated_proactive_cost_usd": branch_b_cost,
                "fits_remaining_budget": branch_b_cost <= remaining_budget,
                "budget_delta_usd": remaining_budget - branch_b_cost,
                "tradeoff_note": "Maximizes retention protection across all high and solid performers, but may require a budget reallocation if cost exceeds remaining holdback.",
            },
            {
                "branch_id": "Branch_C_Targeted_High_Performer_Bridge_And_Joint_Offer_Calibration",
                "description": "Fully fund Tier 2 and Tier 3 high performers facing >15% cliffs while partnering with the Offers Desk to recalibrate hiring bands for affected job families.",
                "estimated_proactive_cost_usd": branch_c_cost,
                "fits_remaining_budget": branch_c_cost <= remaining_budget,
                "budget_delta_usd": remaining_budget - branch_c_cost,
                "tradeoff_note": "Balances high-regret retention with fiscal discipline and aligns proactive grants with reactive offer band adjustments.",
            },
        ],
    }
