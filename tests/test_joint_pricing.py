"""Unit tests for joint pricing: a base lift and a promotion for the same employee count once."""

from pathlib import Path
import sys
import tempfile
import unittest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
for path in (PROJECT_ROOT, Path(__file__).resolve().parent):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from src.tools.intervention_fit import POLICY, assess_intervention_fit, next_level_reference  # noqa: E402
from test_intervention_fit import FAMILY, ORG, REFRESH, _lever, _losses, _make_db, _option, _person  # noqa: E402


class JointPricingFixtureTest(unittest.TestCase):

    def test_a_lift_and_a_promotion_for_one_employee_count_once(self) -> None:
        roster = [
            _person("BOTH", "IC3", 0.90, 230000.0, rating="rating_4"),                # lift and promotion
            _person("LIFT", "IC2", 0.90, 200000.0),                                    # lift only, rating 3
            _person("PROMO", "IC2", 0.97, 185000.0, rating="rating_5"),                # above 0.95, promotion only
            _person("HELD", "IC2", 0.90, 185000.0, rating="rating_4", prior_grant=1),  # Tier 0 lift, promotion only
        ]
        with tempfile.TemporaryDirectory() as tmp:
            offers = _losses("Reactive_Counter_Offer", {"Level_Up_Offer": 2, "Base_Salary_Cap": 1, "Total_Equity_Size": 1})
            mismatch = assess_intervention_fit(ORG, FAMILY, _make_db(Path(tmp) / "mismatch.db", roster, offers))
            offers = _losses("Reactive_Counter_Offer", {"Total_Equity_Size": 3, "Base_Salary_Cap": 1})
            fit = assess_intervention_fit(ORG, FAMILY, _make_db(Path(tmp) / "fit.db", roster, offers))
        # BOTH's lift would cost 11,500 in base (207,000 to 218,500) and 2,300 in bonus at 20 percent.
        self.assertEqual(mismatch["joint_pricing"]["employees"], 1)
        self.assertEqual(mismatch["joint_pricing"]["credit_usd"], 13800.0)
        self.assertEqual(_lever(mismatch, "base_adjustment")["candidates"], 2)
        self.assertEqual(_lever(mismatch, "level_review")["costed"], 3)
        self.assertEqual([_option(mismatch, k)["joint_pricing_credit_usd"] for k in "ABC"], [0.0, 0.0, 13800.0])
        # Without the mismatch, Option C carries neither lever, so nothing is credited.
        self.assertEqual(_option(fit, "C")["joint_pricing_credit_usd"], 0.0)
        # The credit is safe: the promotion's low case already lifts BOTH past this level's 0.95 ceiling.
        next_mrp, _ = next_level_reference("IC3", "TEST_ZONE", 230000.0, REFRESH["IC3"])
        self.assertGreater(round(POLICY["compa_floor"] * next_mrp, -2), round(POLICY["compa_lift_max"] * 230000.0, -2))


class JointPricingSyntheticTest(unittest.TestCase):

    def test_two_cohorts_change_and_research_scientists_stay_over_budget(self) -> None:
        scientists = assess_intervention_fit("VP_CLOUD_AI", "RESEARCH_SCI")
        self.assertEqual(scientists["joint_pricing"]["employees"], 7)
        self.assertEqual(_option(scientists, "C")["joint_pricing_credit_usd"], 121800.0)
        self.assertEqual(_option(scientists, "C")["first_year_cost_usd"], 3884800.0)
        self.assertEqual(_option(scientists, "C")["budget_gap_usd"], 1734800.0)
        sre = assess_intervention_fit("VP_INFRA_SRE", "SRE_ENG")
        self.assertEqual(sre["joint_pricing"]["employees"], 1)
        self.assertEqual(_option(sre, "C")["joint_pricing_credit_usd"], 7400.0)
        self.assertEqual(_option(sre, "C")["first_year_cost_usd"], 257400.0)
        self.assertTrue(_option(sre, "C")["fits_remaining_budget"])


if __name__ == "__main__":
    unittest.main()
