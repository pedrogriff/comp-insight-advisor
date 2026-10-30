"""Unit tests for the driver-fit tool that matches retention levers to loss drivers."""

from contextlib import closing
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
import unittest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.tools.deterministic_analytics import simulate_proactive_retention_scenarios
from src.tools.intervention_fit import (
    DRIVERS,
    LEVERS,
    POLICY,
    TIER0_RATINGS,
    assess_intervention_fit,
    next_level_reference,
)

PLAYBOOK = PROJECT_ROOT / "docs" / "policies" / "compensation_governance_playbook.md"
ORG, FAMILY = "VP_TEST", "TEST_FAM"
BONUS = {"IC1": 0.15, "IC2": 0.15, "IC3": 0.20, "IC4": 0.25, "IC5": 0.30}
REFRESH = {"IC1": 45000, "IC2": 80000, "IC3": 140000, "IC4": 250000, "IC5": 450000}


def _person(emp: str, level: str, compa: float, mrp: float, cliff: bool = True, rating: str = "rating_3",
            promoted: int = 0, tenure: float = 3.0, prior_grant: int = 0) -> tuple:
    base = round(mrp * compa, -2)
    yoy = -20.0 if cliff else 1.0
    return (emp, ORG, FAMILY, level, "TEST_ZONE", rating, "None", promoted, tenure, base, mrp, compa,
            BONUS[level], REFRESH[level], 300000.0, 300000.0 * (1 + yoy / 100), yoy, prior_grant)


def _losses(event_type: str, drivers: dict[str, int], won: int = 0) -> list[tuple]:
    rows = [(ORG, FAMILY, event_type, "Accepted_Retained", "None")] * won
    for driver, count in drivers.items():
        rows += [(ORG, FAMILY, event_type, "Declined_Lost", driver)] * count
    return rows


def _make_db(path: Path, roster: list[tuple], offers: list[tuple], remaining: float = 1_000_000.0) -> Path:
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute(
            "CREATE TABLE org_roster_cashflows (employee_id TEXT, vp_org_code TEXT, job_family TEXT,"
            " job_level TEXT, region TEXT, rating_2025 TEXT, critical_ai_talent_tier TEXT,"
            " promoted_last_6m INTEGER, tenure_years REAL, base_salary_usd REAL, market_reference_usd REAL,"
            " compa_ratio REAL, bonus_target_pct REAL, equity_refresh_guideline_usd REAL,"
            " intended_cashflow_2026_usd REAL, intended_cashflow_2027_usd REAL,"
            " yoy_cashflow_change_26_to_27_pct REAL, prior_proactive_grant_24m INTEGER)"
        )
        conn.execute(
            "CREATE TABLE reactive_offers_counters (vp_org_code TEXT, job_family TEXT, event_type TEXT,"
            " outcome TEXT, primary_loss_driver TEXT)"
        )
        conn.execute("CREATE TABLE department_budgets (vp_org_code TEXT, proactive_remaining_usd REAL)")
        conn.executemany("INSERT INTO org_roster_cashflows VALUES (" + ",".join("?" * 18) + ")", roster)
        conn.executemany("INSERT INTO reactive_offers_counters VALUES (?,?,?,?,?)", offers)
        conn.execute("INSERT INTO department_budgets VALUES (?, ?)", (ORG, remaining))
    return path


def _lever(result: dict, key: str) -> dict:
    return next(item for item in result["levers"] if item["lever"] == key)


def _option(result: dict, key: str) -> dict:
    return next(item for item in result["options"] if item["option"] == key)


class FixtureTest(unittest.TestCase):

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _run(self, roster: list[tuple], departures: dict[str, int], declined: dict[str, int],
             remaining: float = 1_000_000.0) -> dict:
        offers = _losses("Reactive_Counter_Offer", departures, won=3) + _losses("New_Hire_Offer", declined, won=5)
        self._runs = getattr(self, "_runs", 0) + 1
        db = _make_db(self.dir / f"fit_{self._runs}.db", roster, offers, remaining)
        return assess_intervention_fit(ORG, FAMILY, db)

    def test_departures_and_declined_offers_are_counted_apart(self) -> None:
        result = self._run([], {"Level_Up_Offer": 2, "Base_Salary_Cap": 1}, {"Total_Equity_Size": 4})
        self.assertEqual(result["departures"]["total"], 3)
        self.assertEqual(result["departures"]["by_driver"]["Level_Up_Offer"], 2)
        self.assertEqual(result["declined_offers"]["total"], 4)
        self.assertEqual(result["declined_offers"]["by_driver"]["Total_Equity_Size"], 4)
        self.assertEqual(set(result["departures"]["by_driver"]), set(DRIVERS))

    def test_each_lever_counts_only_the_drivers_it_addresses(self) -> None:
        result = self._run([], {"Level_Up_Offer": 2, "Base_Salary_Cap": 1, "Total_Equity_Size": 1},
                           {"Base_Salary_Cap": 2, "Cashflow_Year1_Gap": 3})
        self.assertEqual(_lever(result, "retention_grant")["departures_addressed"], 1)
        self.assertEqual(_lever(result, "base_adjustment")["departures_addressed"], 1)
        self.assertEqual(_lever(result, "level_review")["departures_addressed"], 2)
        self.assertEqual(_lever(result, "offer_band_review")["departures_addressed"], 0)
        self.assertEqual(_lever(result, "offer_band_review")["declined_offers_addressed"], 5)
        self.assertEqual(_lever(result, "retention_grant")["declined_offers_addressed"], 0)

    def test_mismatch_flag_fires_below_half_and_not_at_half(self) -> None:
        below = self._run([], {"Level_Up_Offer": 2, "Base_Salary_Cap": 1, "Total_Equity_Size": 1}, {})
        self.assertTrue(below["flags"]["default_lever_mismatch"])
        at_half = self._run([], {"Base_Salary_Cap": 2, "Total_Equity_Size": 2}, {})
        self.assertFalse(at_half["flags"]["default_lever_mismatch"])

    def test_thin_evidence_below_five_departures(self) -> None:
        four = self._run([], {"Total_Equity_Size": 4}, {})
        self.assertTrue(four["flags"]["thin_driver_evidence"])
        self.assertIn("4 departures", four["settle_it"])
        five = self._run([], {"Total_Equity_Size": 5}, {})
        self.assertFalse(five["flags"]["thin_driver_evidence"])

    def test_calibration_flag_follows_level_departures(self) -> None:
        self.assertTrue(self._run([], {"Level_Up_Offer": 1}, {})["flags"]["needs_calibration"])
        self.assertFalse(self._run([], {"Base_Salary_Cap": 1}, {"Level_Up_Offer": 3})["flags"]["needs_calibration"])

    def test_base_lift_stops_at_095_and_never_lowers_pay(self) -> None:
        roster = [
            _person("E1", "IC2", 0.90, 200000.0),               # 180,000 lifts to 190,000
            _person("E2", "IC2", 0.97, 200000.0),               # already above 0.95, untouched
            _person("E3", "IC2", 0.95, 200000.0),               # exactly 0.95, untouched
            _person("E4", "IC2", 0.85, 200000.0, cliff=False),  # no cliff, not a retention lift
        ]
        base = _lever(self._run(roster, {"Base_Salary_Cap": 1}, {}), "base_adjustment")
        self.assertEqual(base["candidates"], 1)
        self.assertEqual(base["annual_base_increase_usd"], 10000)
        self.assertEqual(base["annual_bonus_target_increase_usd"], 1500)
        self.assertEqual(base["annual_cost_usd"], 11500)

    def test_floor_breaches_lift_to_080_across_the_cohort(self) -> None:
        roster = [_person("E1", "IC2", 0.78, 200000.0, cliff=False), _person("E2", "IC2", 0.83, 200000.0, cliff=False)]
        result = self._run(roster, {}, {})
        self.assertEqual(result["governance"]["compa_floor_breaches"], 1)
        self.assertEqual(result["governance"]["compa_floor_fix_usd"], 4000)
        self.assertTrue(result["flags"]["compa_floor_breach"])

    def test_base_lift_holds_tier0_but_the_floor_still_applies(self) -> None:
        roster = [
            _person("LOW", "IC2", 0.78, 200000.0, rating="rating_1"),   # Tier 0: floor to 160,000, no lift
            _person("WEAK", "IC2", 0.90, 200000.0, rating="rating_2"),  # Tier 0: no lift
            _person("GRANTED", "IC2", 0.90, 200000.0, prior_grant=1),   # grant in 24 months: no lift
            _person("OK", "IC2", 0.90, 200000.0),                       # 180,000 lifts to 190,000
        ]
        result = self._run(roster, {"Base_Salary_Cap": 1}, {})
        base = _lever(result, "base_adjustment")
        self.assertEqual(base["candidates"], 1)
        self.assertEqual(base["held_by_tier0"], 3)
        self.assertEqual(base["annual_base_increase_usd"], 10000)
        self.assertEqual(result["governance"]["compa_floor_breaches"], 1)
        self.assertEqual(result["governance"]["compa_floor_fix_usd"], 4000)

    def test_promotion_cost_uses_the_next_level_reference(self) -> None:
        roster = [_person("E1", "IC3", 0.90, 230000.0, rating="rating_4")]
        level = _lever(self._run(roster, {"Level_Up_Offer": 1}, {}), "level_review")
        self.assertEqual(level["candidates"], 1)
        self.assertEqual(level["annual_base_increase_usd"], 21000)        # 207,000 to 228,000
        self.assertEqual(level["annual_base_increase_high_usd"], 63800)   # 207,000 to 270,800
        self.assertEqual(level["annual_bonus_target_increase_usd"], 15600)
        self.assertEqual(level["annual_equity_guideline_increase_usd"], 110000)
        self.assertEqual(level["annual_cost_usd"], 146600)
        self.assertEqual(level["annual_cost_high_usd"], 200100)

    def test_level_review_eligibility_rules(self) -> None:
        roster = [
            _person("OK", "IC2", 0.90, 185000.0, rating="rating_5"),
            _person("TOP", "IC5", 0.90, 350000.0, rating="rating_4"),
            _person("NEW", "IC2", 0.90, 185000.0, rating="rating_4", tenure=1.5),
            _person("PROMO", "IC2", 0.90, 185000.0, rating="rating_4", promoted=1),
            _person("MID", "IC2", 0.90, 185000.0, rating="rating_3"),
            _person("CALM", "IC2", 0.90, 185000.0, rating="rating_4", cliff=False),
        ]
        level = _lever(self._run(roster, {"Level_Up_Offer": 1}, {}), "level_review")
        self.assertEqual(level["candidates"], 2)
        self.assertEqual(level["costed"], 1)
        self.assertEqual(level["at_top_level"], 1)

    def test_option_c_adds_base_and_level_only_on_mismatch(self) -> None:
        mismatch = self._run([], {"Level_Up_Offer": 2, "Base_Salary_Cap": 1, "Total_Equity_Size": 1}, {})
        self.assertIn("base_adjustment", _option(mismatch, "C")["levers"])
        self.assertIn("level_review", _option(mismatch, "C")["levers"])
        self.assertEqual(_option(mismatch, "C")["departures_addressed"], 4)
        self.assertTrue(_option(mismatch, "B")["partial_fit"])
        fit = self._run([], {"Total_Equity_Size": 3, "Base_Salary_Cap": 1}, {})
        self.assertNotIn("base_adjustment", _option(fit, "C")["levers"])
        self.assertFalse(_option(fit, "B")["partial_fit"])

    def test_option_costs_add_lever_costs_to_grant_branches(self) -> None:
        # E1 is costed for a promotion only and E2 for a lift only. tests/test_joint_pricing.py covers one person with both.
        roster = [_person("E1", "IC3", 0.97, 230000.0, rating="rating_4"), _person("E2", "IC2", 0.90, 200000.0)]
        offers = _losses("Reactive_Counter_Offer", {"Level_Up_Offer": 2, "Base_Salary_Cap": 1, "Total_Equity_Size": 1})
        db = _make_db(self.dir / "cost.db", roster, offers, remaining=200000.0)
        result = assess_intervention_fit(ORG, FAMILY, db)
        branches = {b["branch_id"]: b["estimated_proactive_cost_usd"]
                    for b in simulate_proactive_retention_scenarios(ORG, FAMILY, db)["strategic_branches"]}
        option_c = _option(result, "C")
        expected = (branches["Branch_C_Targeted_High_Performer_Bridge_And_Joint_Offer_Calibration"]
                    + _lever(result, "base_adjustment")["annual_cost_usd"]
                    + _lever(result, "level_review")["annual_cost_usd"])
        self.assertEqual(option_c["first_year_cost_usd"], expected)
        self.assertEqual(option_c["fits_remaining_budget"], expected <= 200000.0)
        self.assertEqual(option_c["budget_gap_usd"], max(0, expected - 200000.0))
        self.assertEqual(_option(result, "B")["first_year_cost_usd"],
                         branches["Branch_B_Full_Proactive_Cliff_Coverage"])

    def test_unknown_job_family_returns_empty_counts(self) -> None:
        db = _make_db(self.dir / "empty.db", [], [])
        result = assess_intervention_fit(ORG, "NOT_A_FAMILY", db)
        self.assertEqual(result["departures"]["total"], 0)
        self.assertFalse(result["flags"]["default_lever_mismatch"])
        self.assertTrue(result["flags"]["thin_driver_evidence"])
        self.assertIsNone(result["leading_lever"])


class SyntheticDatabaseTest(unittest.TestCase):

    def test_research_scientists_match_the_documented_example(self) -> None:
        result = assess_intervention_fit("VP_CLOUD_AI", "RESEARCH_SCI")
        self.assertEqual(result["departures"]["by_driver"],
                         {"Total_Equity_Size": 1, "Cashflow_Year1_Gap": 0, "Base_Salary_Cap": 1, "Level_Up_Offer": 2})
        self.assertEqual(result["declined_offers"]["total"], 6)
        self.assertEqual(_lever(result, "retention_grant")["departures_addressed"], 1)
        self.assertTrue(result["flags"]["default_lever_mismatch"])
        self.assertTrue(result["flags"]["thin_driver_evidence"])
        self.assertTrue(result["flags"]["needs_calibration"])
        self.assertEqual(result["leading_lever"], "level_review")
        self.assertEqual(_lever(result, "base_adjustment")["candidates"], 18)
        self.assertEqual(_lever(result, "base_adjustment")["held_by_tier0"], 9)
        self.assertEqual(_lever(result, "retention_grant")["held_by_tier0"], 9)
        # Option C, with its joint pricing credit, is pinned in tests/test_joint_pricing.py.
        self.assertEqual([o["first_year_cost_usd"] for o in result["options"]][:2], [1524000.0, 2648000.0])
        self.assertEqual(_lever(result, "level_review")["candidates"], 9)
        self.assertEqual(result["governance"]["compa_floor_breaches"], 5)
        self.assertEqual(_option(result, "C")["departures_addressed"], 4)

    def test_ai_ml_engineers_fit_the_retention_grant(self) -> None:
        result = assess_intervention_fit("VP_CLOUD_AI", "AI_ML_ENG")
        self.assertEqual(result["departures"]["total"], 7)
        self.assertEqual(_lever(result, "retention_grant")["departures_addressed"], 6)
        self.assertFalse(result["flags"]["default_lever_mismatch"])
        self.assertNotIn("base_adjustment", _option(result, "C")["levers"])

    def test_next_level_reference_matches_the_synthetic_ladder(self) -> None:
        with closing(sqlite3.connect(PROJECT_ROOT / "data" / "synthetic" / "comp_insight_advisor.db")) as conn:
            ladder = {(region, level): (mrp, guideline) for region, level, mrp, guideline in conn.execute(
                "SELECT region, job_level, MAX(market_reference_usd), MAX(equity_refresh_guideline_usd)"
                " FROM org_roster_cashflows GROUP BY 1, 2")}
        order = ["IC1", "IC2", "IC3", "IC4", "IC5"]
        checked = 0
        for (region, level), (mrp, guideline) in ladder.items():
            nxt = order[order.index(level) + 1] if level != "IC5" else None
            if nxt and (region, nxt) in ladder:
                self.assertEqual(next_level_reference(level, region, mrp, guideline), ladder[(region, nxt)])
                checked += 1
        self.assertIsNone(next_level_reference("IC5", "US_ZONE_A", 402500.0, 517500.0))
        self.assertGreaterEqual(checked, 20)


class PlaybookConsistencyTest(unittest.TestCase):

    def test_levers_match_playbook_section_6(self) -> None:
        text = PLAYBOOK.read_text(encoding="utf-8")
        section = text.split("## Section 6.", 1)[1]
        for key, spec in LEVERS.items():
            row = next(line for line in section.splitlines() if line.startswith("|") and f"`{key}`" in line)
            named = set(re.findall(r"`(" + "|".join(DRIVERS) + r")`", row))
            self.assertEqual(named, set(spec["addresses"]), key)

    def test_policy_numbers_appear_in_the_playbook(self) -> None:
        section = PLAYBOOK.read_text(encoding="utf-8").split("## Section 6.", 1)[1]
        for value in (POLICY["compa_floor"], POLICY["compa_lift_max"]):
            self.assertIn(f"{value:.2f}", section)
        lift_rules = section.split("### 6.2", 1)[1].split("### 6.3", 1)[0]
        self.assertIn("Tier 0", lift_rules)
        for rating in TIER0_RATINGS:
            self.assertIn(f"`{rating}`", lift_rules)


if __name__ == "__main__":
    unittest.main()
