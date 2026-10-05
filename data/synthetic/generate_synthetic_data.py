"""Deterministic synthetic dataset generator for the CMU Agentic AI Capstone.

Uses only the Python standard library (csv, random, sqlite3, pathlib) so it
runs out-of-the-box on any machine before installing external packages.

Generates three relational tables in CSV and SQLite format representing a
fictional 2,000-employee enterprise technology company ("Apex Cloud & AI Corp"):
1. org_roster_cashflows (2,000 employees across 4 VP organizations)
2. reactive_offers_counters (350 new-hire offers and reactive counter-offers)
3. department_budgets (4 VP organization retention and counter-offer budgets)
"""

import csv
from pathlib import Path
import random
import sqlite3
from typing import Any


def weighted_choice(rng: random.Random, items: list[Any], weights: list[float]) -> Any:
    return rng.choices(items, weights=weights, k=1)[0]


def clip(val: float, low: float, high: float) -> float:
    return max(low, min(high, val))


def generate_datasets(output_dir: Path, seed: int = 42) -> None:
    rng = random.Random(seed)
    output_dir.mkdir(parents=True, exist_ok=True)

    vp_orgs = [
        ("VP_CLOUD_AI", "Elena Rostova", "Cloud AI & Machine Learning"),
        ("VP_INFRA_SRE", "Marcus Vance", "Core Infrastructure & SRE"),
        ("VP_ENT_APPS", "Priya Nair", "Enterprise Productivity Apps"),
        ("VP_SEC_INTEL", "Devon Brooks", "Threat Intelligence & Security"),
    ]

    job_families = {
        "VP_CLOUD_AI": ["AI_ML_ENG", "RESEARCH_SCI", "SW_ENG", "PROD_MGMT"],
        "VP_INFRA_SRE": ["SRE_ENG", "SW_ENG", "SYS_NET_ENG", "TECH_PROG_MGMT"],
        "VP_ENT_APPS": ["SW_ENG", "UX_DESIGN", "PROD_MGMT", "DATA_SCI"],
        "VP_SEC_INTEL": ["CYBER_SEC_ENG", "THREAT_RES", "SW_ENG", "SEC_OPS"],
    }

    regions = [
        ("US_BAY_AREA", 1.15),
        ("US_SEATTLE_NYC", 1.10),
        ("US_AUSTIN_DENVER", 0.95),
        ("UK_LONDON", 0.85),
        ("EU_ZURICH_MUNICH", 0.92),
        ("APAC_SINGAPORE_TOKYO", 0.80),
    ]

    level_base_mrp = {
        "L4": (145000, 0.15, 45000),
        "L5": (185000, 0.15, 80000),
        "L6": (230000, 0.20, 140000),
        "L7": (285000, 0.25, 250000),
        "L8": (350000, 0.30, 450000),
    }

    ratings = [
        "1_Needs_Improvement",
        "2_Moderate_Impact",
        "3_Significant_Impact",
        "4_Outstanding_Impact",
        "5_Transformative_Impact",
    ]
    rating_probs = [0.04, 0.16, 0.55, 0.20, 0.05]

    roster_rows: list[dict[str, Any]] = []
    emp_id_counter = 10001

    for vp_code, vp_name, vp_title in vp_orgs:
        org_size = 500
        manager_ids = []
        for m_idx in range(40):
            emp_id = f"EMP{emp_id_counter}"
            emp_id_counter += 1
            lvl = weighted_choice(rng, ["L6", "L7", "L8"], [0.60, 0.30, 0.10])
            jf = rng.choice(job_families[vp_code])
            reg_code, reg_mult = rng.choice(regions)
            base_mrp, bonus_pct, refresh_target = level_base_mrp[lvl]
            mrp_usd = round(base_mrp * reg_mult, -2)
            compa_ratio = round(clip(rng.gauss(0.94, 0.06), 0.80, 1.12), 3)
            base_salary_usd = round(mrp_usd * compa_ratio, -2)
            bonus_usd = round(base_salary_usd * bonus_pct, -2)
            rating_2025 = weighted_choice(rng, ratings, rating_probs)

            icf_2026 = round(
                base_salary_usd + bonus_usd + refresh_target * rng.uniform(0.9, 1.4),
                -2,
            )
            if vp_code == "VP_INFRA_SRE" and m_idx < 4:
                icf_2027 = round(icf_2026 * 0.74, -2)
                governance_note = "Expiring 2024 retention grant creates 2027 cliff"
            else:
                icf_2027 = round(icf_2026 * rng.uniform(0.94, 1.05), -2)
                governance_note = "Clean"

            icf_2028 = round(icf_2027 * rng.uniform(0.95, 1.03), -2)
            yoy_drop_pct = round(((icf_2027 - icf_2026) / icf_2026) * 100.0, 1)
            peer_pct_2026 = int(clip(round(rng.gauss(58, 22)), 5, 99))
            peer_pct_2027 = int(clip(round(peer_pct_2026 + yoy_drop_pct * 1.2), 1, 99))

            manager_ids.append((emp_id, lvl, icf_2026, icf_2027))
            roster_rows.append(
                {
                    "employee_id": emp_id,
                    "vp_org_code": vp_code,
                    "vp_leader_name": vp_name,
                    "vp_org_name": vp_title,
                    "manager_id": vp_code,
                    "is_people_manager": 1,
                    "job_family": jf,
                    "job_level": lvl,
                    "region": reg_code,
                    "tenure_years": round(rng.uniform(2.5, 11.0), 1),
                    "promoted_last_6m": 0,
                    "rating_2025": rating_2025,
                    "critical_ai_talent_tier": (
                        "Tier_1"
                        if jf in ("AI_ML_ENG", "RESEARCH_SCI", "CYBER_SEC_ENG")
                        and rating_2025 in ("4_Outstanding_Impact", "5_Transformative_Impact")
                        else "None"
                    ),
                    "base_salary_usd": base_salary_usd,
                    "market_reference_usd": mrp_usd,
                    "compa_ratio": compa_ratio,
                    "bonus_target_pct": bonus_pct,
                    "equity_refresh_guideline_usd": round(refresh_target * reg_mult, -2),
                    "intended_cashflow_2026_usd": icf_2026,
                    "intended_cashflow_2027_usd": icf_2027,
                    "intended_cashflow_2028_usd": icf_2028,
                    "yoy_cashflow_change_26_to_27_pct": yoy_drop_pct,
                    "peer_percentile_2026": peer_pct_2026,
                    "peer_percentile_2027": peer_pct_2027,
                    "prior_proactive_grant_24m": 0,
                    "governance_flag": governance_note,
                }
            )

        for _ in range(org_size - 40):
            emp_id = f"EMP{emp_id_counter}"
            emp_id_counter += 1
            mgr_id, mgr_lvl, mgr_icf26, mgr_icf27 = rng.choice(manager_ids)
            lvl = weighted_choice(rng, ["L4", "L5", "L6", "L7"], [0.35, 0.38, 0.22, 0.05])
            jf = rng.choice(job_families[vp_code])
            reg_code, reg_mult = rng.choice(regions)
            base_mrp, bonus_pct, refresh_target = level_base_mrp[lvl]
            mrp_usd = round(base_mrp * reg_mult, -2)
            compa_ratio = round(clip(rng.gauss(0.91, 0.07), 0.76, 1.10), 3)
            base_salary_usd = round(mrp_usd * compa_ratio, -2)
            bonus_usd = round(base_salary_usd * bonus_pct, -2)
            rating_2025 = weighted_choice(rng, ratings, rating_probs)
            promoted_recent = 1 if rng.random() < 0.06 else 0

            icf_2026 = round(
                base_salary_usd + bonus_usd + refresh_target * rng.uniform(0.85, 1.35),
                -2,
            )

            is_hotspot_family = jf in ("AI_ML_ENG", "RESEARCH_SCI", "CYBER_SEC_ENG")
            if is_hotspot_family and rng.random() < 0.38:
                drop_factor = rng.uniform(0.72, 0.83)
                icf_2027 = round(icf_2026 * drop_factor, -2)
            else:
                drop_factor = rng.uniform(0.91, 1.04)
                icf_2027 = round(icf_2026 * drop_factor, -2)

            governance_note = "Clean"
            if vp_code == "VP_INFRA_SRE" and mgr_id in [m[0] for m in manager_ids[:4]] and lvl == "L6":
                icf_2027 = round(mgr_icf27 * 1.08, -2)
                governance_note = f"2027 Manager Inversion vs {mgr_id}"
            elif promoted_recent and compa_ratio < 0.83:
                governance_note = "Stale pre-promotion band mapping suspected"

            icf_2028 = round(icf_2027 * rng.uniform(0.94, 1.02), -2)
            yoy_drop_pct = round(((icf_2027 - icf_2026) / icf_2026) * 100.0, 1)
            peer_pct_2026 = int(clip(round(rng.gauss(52, 24)), 1, 99))
            peer_pct_2027 = int(clip(round(peer_pct_2026 + yoy_drop_pct * 1.3), 1, 99))

            roster_rows.append(
                {
                    "employee_id": emp_id,
                    "vp_org_code": vp_code,
                    "vp_leader_name": vp_name,
                    "vp_org_name": vp_title,
                    "manager_id": mgr_id,
                    "is_people_manager": 0,
                    "job_family": jf,
                    "job_level": lvl,
                    "region": reg_code,
                    "tenure_years": round(rng.uniform(0.5, 9.0), 1),
                    "promoted_last_6m": promoted_recent,
                    "rating_2025": rating_2025,
                    "critical_ai_talent_tier": (
                        "Tier_1"
                        if is_hotspot_family
                        and rating_2025 in ("4_Outstanding_Impact", "5_Transformative_Impact")
                        else ("Tier_2" if is_hotspot_family else "None")
                    ),
                    "base_salary_usd": base_salary_usd,
                    "market_reference_usd": mrp_usd,
                    "compa_ratio": compa_ratio,
                    "bonus_target_pct": bonus_pct,
                    "equity_refresh_guideline_usd": round(refresh_target * reg_mult, -2),
                    "intended_cashflow_2026_usd": icf_2026,
                    "intended_cashflow_2027_usd": icf_2027,
                    "intended_cashflow_2028_usd": icf_2028,
                    "yoy_cashflow_change_26_to_27_pct": yoy_drop_pct,
                    "peer_percentile_2026": peer_pct_2026,
                    "peer_percentile_2027": peer_pct_2027,
                    "prior_proactive_grant_24m": 1 if rng.random() < 0.08 else 0,
                    "governance_flag": governance_note,
                }
            )

    competitors = [
        "FrontierLab AI",
        "NovaScale Cloud",
        "Aegis Cyber",
        "Hyperion Compute",
        "Veridian Systems",
    ]
    offer_rows: list[dict[str, Any]] = []
    for idx in range(1, 351):
        event_id = f"OFFER{2026000 + idx}"
        vp_code, _, _ = rng.choice(vp_orgs)
        jf = rng.choice(job_families[vp_code])
        lvl = weighted_choice(rng, ["L4", "L5", "L6", "L7"], [0.30, 0.40, 0.22, 0.08])
        reg_code, _ = rng.choice(regions)
        probs = [0.45, 0.55] if jf in ("AI_ML_ENG", "CYBER_SEC_ENG") else [0.65, 0.35]
        event_type = weighted_choice(rng, ["New_Hire_Offer", "Reactive_Counter_Offer"], probs)
        comp_firm = rng.choice(competitors)
        if jf in ("AI_ML_ENG", "RESEARCH_SCI", "CYBER_SEC_ENG"):
            accepted = rng.random() < 0.52
            competing_premium_pct = round(rng.uniform(18.0, 42.0), 1)
        else:
            accepted = rng.random() < 0.84
            competing_premium_pct = round(rng.uniform(5.0, 18.0), 1)

        offer_rows.append(
            {
                "event_id": event_id,
                "quarter": weighted_choice(rng, ["2026_Q1", "2026_Q2", "2026_Q3"], [0.25, 0.35, 0.40]),
                "vp_org_code": vp_code,
                "job_family": jf,
                "job_level": lvl,
                "region": reg_code,
                "event_type": event_type,
                "competing_employer": comp_firm,
                "competing_offer_premium_pct": competing_premium_pct,
                "our_offer_multiplier": round(rng.uniform(1.0, 1.45), 2),
                "outcome": "Accepted_Retained" if accepted else "Declined_Lost",
                "primary_loss_driver": (
                    "None"
                    if accepted
                    else rng.choice(
                        [
                            "Cashflow_Year1_Gap",
                            "Total_Equity_Size",
                            "Level_Up_Offer",
                            "Base_Salary_Cap",
                        ]
                    )
                ),
                "counter_offer_grant_usd": (
                    round(rng.uniform(80000, 350000), -3)
                    if event_type == "Reactive_Counter_Offer" and accepted
                    else 0.0
                ),
            }
        )

    budget_rows: list[dict[str, Any]] = [
        {
            "vp_org_code": "VP_CLOUD_AI",
            "vp_leader_name": "Elena Rostova",
            "annual_proactive_budget_usd": 12000000,
            "proactive_spent_ytd_usd": 9850000,
            "proactive_remaining_usd": 2150000,
            "reactive_counter_spent_ytd_usd": 6400000,
            "reconciliation_status": "Warning: $1.2M verbal counter-offer miscoded under proactive ledger",
        },
        {
            "vp_org_code": "VP_INFRA_SRE",
            "vp_leader_name": "Marcus Vance",
            "annual_proactive_budget_usd": 9500000,
            "proactive_spent_ytd_usd": 3100000,
            "proactive_remaining_usd": 6400000,
            "reactive_counter_spent_ytd_usd": 2900000,
            "reconciliation_status": "Clean: High remaining proactive capacity for Q4 cliff mitigation",
        },
        {
            "vp_org_code": "VP_ENT_APPS",
            "vp_leader_name": "Priya Nair",
            "annual_proactive_budget_usd": 5200000,
            "proactive_spent_ytd_usd": 4150000,
            "proactive_remaining_usd": 1050000,
            "reactive_counter_spent_ytd_usd": 1800000,
            "reconciliation_status": "Clean: Tracking on target for Q4",
        },
        {
            "vp_org_code": "VP_SEC_INTEL",
            "vp_leader_name": "Devon Brooks",
            "annual_proactive_budget_usd": 4000000,
            "proactive_spent_ytd_usd": 1100000,
            "proactive_remaining_usd": 2900000,
            "reactive_counter_spent_ytd_usd": 3450000,
            "reconciliation_status": "Alert: Reactive counter spend exceeded proactive spend by 3.1x in Q3",
        },
    ]

    def write_csv_and_table(
        conn: sqlite3.Connection, table_name: str, rows: list[dict[str, Any]]
    ) -> None:
        csv_path = output_dir / f"{table_name}.csv"
        fieldnames = list(rows[0].keys())
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        conn.execute(f"DROP TABLE IF EXISTS {table_name}")
        col_defs = []
        for k, v in rows[0].items():
            if isinstance(v, int):
                col_defs.append(f"{k} INTEGER")
            elif isinstance(v, float):
                col_defs.append(f"{k} REAL")
            else:
                col_defs.append(f"{k} TEXT")
        conn.execute(f"CREATE TABLE {table_name} ({', '.join(col_defs)})")
        placeholders = ", ".join(["?"] * len(fieldnames))
        conn.executemany(
            f"INSERT INTO {table_name} VALUES ({placeholders})",
            [tuple(r[k] for k in fieldnames) for r in rows],
        )

    db_path = output_dir / "comp_insight_advisor.db"
    with sqlite3.connect(db_path) as conn:
        write_csv_and_table(conn, "org_roster_cashflows", roster_rows)
        write_csv_and_table(conn, "reactive_offers_counters", offer_rows)
        write_csv_and_table(conn, "department_budgets", budget_rows)
        conn.commit()

    print(
        f"Generated {len(roster_rows)} roster rows, {len(offer_rows)} offer rows, "
        f"and {len(budget_rows)} budget rows in {output_dir}"
    )


if __name__ == "__main__":
    generate_datasets(Path(__file__).resolve().parent)
