"""Unit tests verifying the deterministic SQLite analytics tools."""

from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import unittest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.tools.deterministic_analytics import (
    DEFAULT_DB_PATH,
    analyze_org_cliff_and_equity_health,
    analyze_reactive_offers_and_counters,
    simulate_proactive_retention_scenarios,
)


class DeterministicAnalyticsTest(unittest.TestCase):

    def test_database_exists(self) -> None:
        self.assertTrue(
            DEFAULT_DB_PATH.exists(),
            f"Expected synthetic SQLite database at {DEFAULT_DB_PATH}",
        )

    def test_org_cliff_and_equity_health(self) -> None:
        result = analyze_org_cliff_and_equity_health("VP_CLOUD_AI")
        self.assertEqual(result["vp_org_code"], "VP_CLOUD_AI")
        self.assertEqual(result["org_summary"]["total_headcount"], 500)
        self.assertGreater(result["org_summary"]["cliff_count_gt_15pct"], 0)
        self.assertEqual(
            result["budget_status"]["proactive_remaining_usd"], 2150000
        )

    def test_reactive_offers_and_counters(self) -> None:
        result = analyze_reactive_offers_and_counters("VP_CLOUD_AI")
        self.assertEqual(result["vp_org_code"], "VP_CLOUD_AI")
        self.assertGreater(len(result["offer_and_counter_breakdown"]), 0)
        self.assertGreater(len(result["policy_escalation_triggers"]), 0)

    def test_proactive_retention_scenarios(self) -> None:
        result = simulate_proactive_retention_scenarios("VP_CLOUD_AI", "AI_ML_ENG")
        self.assertEqual(result["vp_org_code"], "VP_CLOUD_AI")
        self.assertEqual(result["job_family_filter"], "AI_ML_ENG")
        self.assertEqual(len(result["strategic_branches"]), 3)

    def test_tier0_ratings_get_no_grant(self) -> None:
        """Playbook Section 3: nobody rated rating_1 or rating_2 gets a proactive grant."""
        result = simulate_proactive_retention_scenarios("VP_CLOUD_AI", "RESEARCH_SCI")
        with closing(sqlite3.connect(DEFAULT_DB_PATH)) as conn:
            held = conn.execute(
                "SELECT COUNT(*) FROM org_roster_cashflows WHERE vp_org_code = 'VP_CLOUD_AI'"
                " AND job_family = 'RESEARCH_SCI' AND yoy_cashflow_change_26_to_27_pct <= -15.0"
                " AND prior_proactive_grant_24m = 0 AND rating_2025 IN ('rating_1', 'rating_2')"
            ).fetchone()[0]
        self.assertEqual(result["held_by_tier0"], held)
        self.assertEqual(held, 9)
        self.assertEqual(result["eligible_cliff_candidates_by_tier"], {"Tier_1": 0, "Tier_2": 22, "Tier_3": 2})
        costs = {b["branch_id"][:8]: b["estimated_proactive_cost_usd"] for b in result["strategic_branches"]}
        self.assertEqual(costs, {"Branch_A": 1524000.0, "Branch_B": 2648000.0, "Branch_C": 2648000.0})


if __name__ == "__main__":
    unittest.main()
