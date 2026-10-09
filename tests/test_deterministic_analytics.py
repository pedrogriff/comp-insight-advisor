"""Unit tests verifying the deterministic SQLite analytics tools."""

from pathlib import Path
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


if __name__ == "__main__":
    unittest.main()
