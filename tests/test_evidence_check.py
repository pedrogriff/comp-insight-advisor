"""Unit tests for the evidence check on conflicting or thin retention signals."""

from contextlib import closing
from pathlib import Path
import sqlite3
import statistics
import sys
import tempfile
import unittest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.tools.evidence_check import (
    INSUFFICIENT,
    LEANS_RISK,
    LEANS_STABLE,
    RISK,
    STABLE,
    assess_retention_evidence,
    classify,
    mean_interval,
    wilson_interval,
)


def _roster(org: str, family: str, headcount: int, cliffs: int) -> list[tuple]:
    """Cliff rows drop 20 percent at the 20th peer percentile, the rest grow 1 percent."""
    rows = []
    for i in range(headcount):
        if i < cliffs:
            rows.append((org, family, -20.0, "rating_4", 20, 0, 3.0, "Clean"))
        else:
            rows.append((org, family, 1.0, "rating_3", 55, 0, 3.0, "Clean"))
    return rows


def _offers(
    org: str,
    family: str,
    event_type: str,
    won: int,
    lost: int,
    premiums: list[float],
    quarter: str = "2026_Q3",
) -> list[tuple]:
    """Builds won + lost events, cycling through the given premiums."""
    rows = []
    for i in range(won + lost):
        accepted = i < won
        rows.append(
            (
                org,
                family,
                quarter,
                event_type,
                "Accepted_Retained" if accepted else "Declined_Lost",
                premiums[i % len(premiums)],
                "None" if accepted else "Cashflow_Year1_Gap",
            )
        )
    return rows


def _make_db(path: Path, roster: list[tuple], offers: list[tuple]) -> Path:
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute(
            "CREATE TABLE org_roster_cashflows (vp_org_code TEXT, job_family TEXT,"
            " yoy_cashflow_change_26_to_27_pct REAL, rating_2025 TEXT,"
            " peer_percentile_2027 INTEGER, prior_proactive_grant_24m INTEGER,"
            " tenure_years REAL, governance_flag TEXT)"
        )
        conn.execute(
            "CREATE TABLE reactive_offers_counters (vp_org_code TEXT, job_family TEXT,"
            " quarter TEXT, event_type TEXT, outcome TEXT,"
            " competing_offer_premium_pct REAL, primary_loss_driver TEXT)"
        )
        conn.executemany("INSERT INTO org_roster_cashflows VALUES (?,?,?,?,?,?,?,?)", roster)
        conn.executemany("INSERT INTO reactive_offers_counters VALUES (?,?,?,?,?,?,?)", offers)
    return path


class IntervalTest(unittest.TestCase):

    def test_wilson_interval_matches_reference_values(self) -> None:
        self.assertEqual(wilson_interval(7, 13), (29.1, 76.8))
        self.assertEqual(wilson_interval(16, 17), (73.0, 99.0))
        self.assertEqual(wilson_interval(1, 11), (1.6, 37.7))

    def test_wilson_interval_rejects_impossible_counts(self) -> None:
        with self.assertRaises(ValueError):
            wilson_interval(3, 0)
        with self.assertRaises(ValueError):
            wilson_interval(5, 4)

    def test_mean_interval_uses_t_value_for_small_samples(self) -> None:
        values = [10.0, 12.0, 14.0, 16.0, 18.0]
        low, high = mean_interval(values)
        half = 2.776 * statistics.stdev(values) / 5 ** 0.5
        self.assertAlmostEqual(low, 14.0 - half)
        self.assertAlmostEqual(high, 14.0 + half)


class ClassifyTest(unittest.TestCase):

    def test_rules(self) -> None:
        cases = [
            (RISK, [RISK, RISK, LEANS_RISK], ("CONVERGENT", "STRONG")),
            (RISK, [LEANS_RISK, LEANS_RISK, RISK], ("CONVERGENT", "MODERATE")),
            (RISK, [STABLE, LEANS_STABLE, STABLE], ("INTERNAL_ONLY", "STRONG")),
            (RISK, [STABLE, LEANS_RISK, INSUFFICIENT], ("INTERNAL_ONLY", "MODERATE")),
            (RISK, [LEANS_RISK, LEANS_STABLE, INSUFFICIENT], ("INCONCLUSIVE", "WEAK")),
            (RISK, [RISK, STABLE, LEANS_RISK], ("INCONCLUSIVE", "WEAK")),
            (STABLE, [RISK, RISK, STABLE], ("MARKET_ONLY", "MODERATE")),
            (STABLE, [STABLE, STABLE, LEANS_RISK], ("NO_SIGNAL", "STRONG")),
            (STABLE, [LEANS_STABLE, LEANS_STABLE, INSUFFICIENT], ("NO_SIGNAL", "WEAK")),
            (INSUFFICIENT, [RISK, RISK, RISK], ("INSUFFICIENT_DATA", "WEAK")),
            (RISK, [INSUFFICIENT, INSUFFICIENT, INSUFFICIENT], ("INSUFFICIENT_DATA", "WEAK")),
        ]
        for internal, market, expected in cases:
            with self.subTest(internal=internal, market=market):
                self.assertEqual(classify(internal, market), expected)


class SyntheticDatabaseTest(unittest.TestCase):
    """Runs against data/synthetic/comp_insight_advisor.db."""

    def test_convergent_strong_when_both_sources_agree(self) -> None:
        result = assess_retention_evidence("VP_CLOUD_AI", "AI_ML_ENG")
        self.assertEqual(result["pattern"], "CONVERGENT")
        self.assertEqual(result["evidence_strength"], "STRONG")
        self.assertTrue(result["retention_spend_supported"])
        self.assertEqual(result["next_step"], "retrieve_policy")

    def test_thin_offer_data_lowers_strength_and_requires_disclosure(self) -> None:
        result = assess_retention_evidence("VP_CLOUD_AI", "RESEARCH_SCI")
        self.assertEqual(result["pattern"], "CONVERGENT")
        self.assertEqual(result["evidence_strength"], "MODERATE")
        self.assertTrue(result["uncertainty_disclosure_required"])
        acceptance = result["indicators"][1]
        self.assertEqual(acceptance["indicator"], "new_hire_acceptance")
        self.assertEqual(acceptance["events"], 13)
        self.assertEqual(acceptance["value_pct"], 53.8)
        self.assertEqual(acceptance["interval_95_pct"], [29.1, 76.8])
        self.assertEqual(acceptance["status"], LEANS_RISK)

    def test_policy_trigger_still_fires_when_evidence_is_weak(self) -> None:
        result = assess_retention_evidence("VP_SEC_INTEL", "SEC_OPS")
        self.assertEqual(result["pattern"], "NO_SIGNAL")
        self.assertFalse(result["retention_spend_supported"])
        self.assertEqual(
            result["policy_triggers"],
            ["6 counter-offers in 2026_Q3, above the limit of 5 per quarter."],
        )

    def test_unknown_job_family_is_insufficient(self) -> None:
        result = assess_retention_evidence("VP_CLOUD_AI", "NOT_A_FAMILY")
        self.assertEqual(result["pattern"], "INSUFFICIENT_DATA")
        self.assertEqual(result["next_step"], "widen_scope")
        pooled = assess_retention_evidence(None, "NOT_A_FAMILY")
        self.assertEqual(pooled["scope"]["vp_org_code"], "ALL_ORGS")
        self.assertEqual(pooled["next_step"], "report_data_gap")


class FixtureDatabaseTest(unittest.TestCase):
    """Builds small databases for patterns the synthetic data does not contain."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_cliff_with_stable_market_is_internal_only(self) -> None:
        db = _make_db(
            self.dir / "divergent.db",
            _roster("VP_TEST", "FAMILY_X", 40, 12),
            _offers("VP_TEST", "FAMILY_X", "New_Hire_Offer", 19, 1, [8.0, 10.0, 12.0])
            + _offers("VP_TEST", "FAMILY_X", "Reactive_Counter_Offer", 7, 1, [9.0, 11.0]),
        )
        result = assess_retention_evidence("VP_TEST", "FAMILY_X", db)
        statuses = [i["status"] for i in result["indicators"]]
        self.assertEqual(statuses, [RISK, STABLE, LEANS_STABLE, STABLE])
        self.assertEqual(result["pattern"], "INTERNAL_ONLY")
        self.assertEqual(result["evidence_strength"], "STRONG")
        self.assertFalse(result["retention_spend_supported"])
        self.assertEqual(result["next_step"], "monitor")
        self.assertEqual(result["context"]["high_performer_cliff_count"], 12)
        self.assertEqual(result["context"]["cliff_below_p25_2027"], 12)

    def test_leaning_signals_only_are_inconclusive(self) -> None:
        db = _make_db(
            self.dir / "inconclusive.db",
            _roster("VP_TEST", "FAMILY_Y", 40, 12),
            _offers("VP_TEST", "FAMILY_Y", "New_Hire_Offer", 7, 5, [14.0, 36.0, 20.0])
            + _offers("VP_TEST", "FAMILY_Y", "Reactive_Counter_Offer", 4, 2, [30.0, 16.0]),
        )
        result = assess_retention_evidence("VP_TEST", "FAMILY_Y", db)
        self.assertEqual(result["indicators"][1]["status"], LEANS_RISK)
        self.assertEqual(result["pattern"], "INCONCLUSIVE")
        self.assertEqual(result["evidence_strength"], "WEAK")
        self.assertTrue(result["uncertainty_disclosure_required"])
        self.assertFalse(result["retention_spend_supported"])
        self.assertEqual(result["next_step"], "investigate")

    def test_market_pressure_without_cliffs_goes_to_offers_desk(self) -> None:
        db = _make_db(
            self.dir / "market.db",
            _roster("VP_TEST", "FAMILY_Z", 40, 0),
            _offers("VP_TEST", "FAMILY_Z", "New_Hire_Offer", 4, 11, [28.0, 32.0, 30.0]),
        )
        result = assess_retention_evidence("VP_TEST", "FAMILY_Z", db)
        self.assertEqual(result["pattern"], "MARKET_ONLY")
        self.assertEqual(result["evidence_strength"], "STRONG")
        self.assertEqual(result["next_step"], "refer_offers_desk")
        self.assertEqual(result["indicators"][2]["status"], INSUFFICIENT)
        self.assertEqual(result["context"]["loss_drivers"], {"Cashflow_Year1_Gap": 11})

    def test_thin_org_data_widens_to_all_orgs(self) -> None:
        db = _make_db(
            self.dir / "thin.db",
            _roster("VP_SMALL", "FAMILY_W", 30, 9) + _roster("VP_LARGE", "FAMILY_W", 40, 0),
            _offers("VP_SMALL", "FAMILY_W", "New_Hire_Offer", 2, 1, [30.0])
            + _offers("VP_LARGE", "FAMILY_W", "New_Hire_Offer", 4, 8, [27.0, 31.0, 29.0]),
        )
        small = assess_retention_evidence("VP_SMALL", "FAMILY_W", db)
        self.assertEqual(small["pattern"], "INSUFFICIENT_DATA")
        self.assertEqual(small["next_step"], "widen_scope")
        self.assertEqual(
            [i["status"] for i in small["indicators"][1:]], [INSUFFICIENT] * 3
        )
        pooled = assess_retention_evidence(None, "FAMILY_W", db)
        self.assertEqual(pooled["scope"]["vp_org_code"], "ALL_ORGS")
        self.assertEqual(pooled["indicators"][0]["value_pct"], 12.9)
        self.assertEqual(pooled["pattern"], "CONVERGENT")
        self.assertEqual(pooled["evidence_strength"], "STRONG")

    def test_counter_volume_trigger_counts_per_quarter(self) -> None:
        db = _make_db(
            self.dir / "volume.db",
            _roster("VP_TEST", "FAMILY_V", 40, 0),
            _offers("VP_TEST", "FAMILY_V", "Reactive_Counter_Offer", 5, 1, [10.0], "2026_Q2")
            + _offers("VP_TEST", "FAMILY_V", "Reactive_Counter_Offer", 4, 1, [10.0], "2026_Q3"),
        )
        result = assess_retention_evidence("VP_TEST", "FAMILY_V", db)
        self.assertEqual(result["context"]["counters_by_quarter"], {"2026_Q2": 6, "2026_Q3": 5})
        self.assertEqual(
            result["policy_triggers"],
            ["6 counter-offers in 2026_Q2, above the limit of 5 per quarter."],
        )


if __name__ == "__main__":
    unittest.main()
