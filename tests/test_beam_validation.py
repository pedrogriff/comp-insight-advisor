"""Unit tests for beam-search pruning validation and multi-cohort scaling. Standard library only."""

from pathlib import Path
import sys
import unittest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.planning.beam_validation import (VP_CLOUD_AI_COHORTS, composable_cohort_front, exhaustive_options,  # noqa: E402
                                          ordered_path_count, plan_org_options, validate_cohort_beam,
                                          validate_org_scaling)
from src.planning.tot_planner import COHORTS, cohort_facts, outcome, search  # noqa: E402


class SingleCohortBeamValidationTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.by_scope = {f"{org} {fam}": validate_cohort_beam(org, fam) for org, fam in COHORTS}

    def test_duplicate_pruning_collapses_162_ordered_paths_to_32_unique_plans(self):
        self.assertEqual(ordered_path_count(), 162)
        for scope, res in self.by_scope.items():
            self.assertEqual(res["exhaustive"]["plans_evaluated"], 32, scope)
            self.assertEqual(res["exhaustive"]["model_calls"], 31, scope)

    def test_exhaustive_pareto_counts_across_three_convergent_cohorts(self):
        counts = {s: len(r["exhaustive"]["pareto"]) for s, r in self.by_scope.items()}
        self.assertEqual(counts, {
            "VP_CLOUD_AI RESEARCH_SCI": 5,
            "VP_CLOUD_AI AI_ML_ENG": 4,
            "VP_SEC_INTEL CYBER_SEC_ENG": 6,
        })

    def test_width_three_matches_all_exhaustive_options_pareto_plans_and_budget_sweeps(self):
        evals, calls, rounds = {}, {}, {}
        for scope, res in self.by_scope.items():
            w3 = res["by_width"][3]
            self.assertTrue(w3["options_match"], scope)
            self.assertTrue(w3["signatures_match"], scope)
            self.assertEqual(w3["missed_options"], [], scope)
            self.assertEqual(w3["missed_pareto"], [], scope)
            self.assertEqual(w3["budget_thresholds_tested"], 35, scope)
            self.assertEqual(w3["budget_option_misses"], 0, scope)
            evals[scope] = w3["evaluations"]
            calls[scope] = w3["model_calls"]
            rounds[scope] = w3["rounds"]

        self.assertEqual(evals, {
            "VP_CLOUD_AI RESEARCH_SCI": 27,
            "VP_CLOUD_AI AI_ML_ENG": 24,
            "VP_SEC_INTEL CYBER_SEC_ENG": 25,
        })
        self.assertEqual(calls, {
            "VP_CLOUD_AI RESEARCH_SCI": 11,
            "VP_CLOUD_AI AI_ML_ENG": 8,
            "VP_SEC_INTEL CYBER_SEC_ENG": 11,
        })
        self.assertEqual(rounds, {
            "VP_CLOUD_AI RESEARCH_SCI": 4,
            "VP_CLOUD_AI AI_ML_ENG": 3,
            "VP_SEC_INTEL CYBER_SEC_ENG": 4,
        })
        self.assertEqual(sum(calls.values()), 30)

    def test_width_one_misses_ai_ml_option_three_and_four_pareto_plans(self):
        ai_w1 = self.by_scope["VP_CLOUD_AI AI_ML_ENG"]["by_width"][1]
        self.assertFalse(ai_w1["options_match"])
        self.assertEqual(len(ai_w1["missed_options"]), 1)
        miss = ai_w1["missed_options"][0]
        self.assertEqual(miss["beam"], "base_adjustment:lift_to_0.95")
        self.assertEqual(miss["exhaustive"], "base_adjustment:lift_to_0.95 + offer_band_review:offers_desk")
        self.assertEqual(miss["beam_outcome"][:3], (1, 0, 294200.0))
        self.assertEqual(miss["exhaustive_outcome"][:3], (1, 10, 294200.0))

        missed_pareto = {s: len(r["by_width"][1]["missed_pareto"]) for s, r in self.by_scope.items()}
        self.assertEqual(missed_pareto, {
            "VP_CLOUD_AI RESEARCH_SCI": 1,
            "VP_CLOUD_AI AI_ML_ENG": 1,
            "VP_SEC_INTEL CYBER_SEC_ENG": 2,
        })
        sweep_misses = sum(r["by_width"][1]["budget_option_misses"] for r in self.by_scope.values())
        self.assertEqual(sweep_misses, 44)

    def test_width_two_misses_cyber_pareto_plan_and_seventeen_budget_thresholds(self):
        cyber_w2 = self.by_scope["VP_SEC_INTEL CYBER_SEC_ENG"]["by_width"][2]
        self.assertEqual(len(cyber_w2["missed_pareto"]), 1)
        missed = cyber_w2["missed_pareto"][0]
        self.assertEqual(
            missed["signature"],
            "base_adjustment:lift_to_0.95 + level_review:promotion_low_case + offer_band_review:offers_desk",
        )
        self.assertEqual(outcome(missed)[:3], (2, 6, 1261200.0))

        sweep_misses = {s: r["by_width"][2]["budget_option_misses"] for s, r in self.by_scope.items()}
        self.assertEqual(sweep_misses, {
            "VP_CLOUD_AI RESEARCH_SCI": 0,
            "VP_CLOUD_AI AI_ML_ENG": 11,
            "VP_SEC_INTEL CYBER_SEC_ENG": 6,
        })

    def test_width_four_spends_more_calls_with_zero_accuracy_gain_over_width_three(self):
        w4_calls = sum(r["by_width"][4]["model_calls"] for r in self.by_scope.values())
        w4_evals = sum(r["by_width"][4]["evaluations"] for r in self.by_scope.values())
        self.assertEqual((w4_evals, w4_calls), (86, 38))
        for res in self.by_scope.values():
            self.assertEqual(
                [(o["role"], outcome(o)) for o in res["by_width"][4]["options"]],
                [(o["role"], outcome(o)) for o in res["by_width"][3]["options"]],
            )


class MultiCohortOrgScalingTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.cloud_ai = validate_org_scaling(VP_CLOUD_AI_COHORTS)
        cls.portfolio = validate_org_scaling(COHORTS)

    def test_shared_vp_cloud_ai_budget_exposes_naive_sum_overflow_and_flat_cap_starvation(self):
        rs_facts = cohort_facts("VP_CLOUD_AI", "RESEARCH_SCI")
        ai_facts = cohort_facts("VP_CLOUD_AI", "AI_ML_ENG")
        rs_top = exhaustive_options(rs_facts)["options"][0]["first_year_cost_usd"]
        ai_top = exhaustive_options(ai_facts)["options"][0]["first_year_cost_usd"]
        self.assertEqual((rs_top, ai_top), (1236800.0, 2009200.0))
        self.assertGreater(rs_top + ai_top, rs_facts["remaining_budget_usd"])

        self.assertEqual(self.cloud_ai["exhaustive_plans"], 1024)
        self.assertEqual(self.cloud_ai["exhaustive_pareto_count"], 12)
        opt1 = self.cloud_ai["exhaustive_options"][0]
        self.assertEqual((opt1["departures_addressed"], opt1["declined_addressed"], opt1["first_year_cost_usd"]),
                         (7, 16, 1995600.0))

        self.assertFalse(self.cloud_ai["flat_by_cap"][40]["options_match"])
        self.assertFalse(self.cloud_ai["flat_by_cap"][40]["pareto_match"])
        self.assertFalse(self.cloud_ai["flat_by_cap"][240]["pareto_match"])

    def test_factored_width_three_recovers_exact_vp_cloud_ai_options_and_pareto_front(self):
        w1 = self.cloud_ai["factored_by_width"][1]
        w2 = self.cloud_ai["factored_by_width"][2]
        w3 = self.cloud_ai["factored_by_width"][3]
        self.assertFalse(w1["options_match"])
        self.assertFalse(w2["pareto_match"])
        self.assertTrue(w3["options_match"])
        self.assertTrue(w3["pareto_match"])
        self.assertEqual((w3["stage1_evaluations"], w3["stage2_evaluations"], w3["evaluations"]), (51, 34, 85))
        self.assertEqual((w3["model_calls"], w3["rounds"]), (22, 5))
        self.assertEqual(w3["candidate_counts"], [7, 5])

    def test_three_cohort_portfolio_breaks_even_raised_flat_cap_while_factored_width_three_is_exact(self):
        self.assertEqual(self.portfolio["exhaustive_plans"], 32768)
        self.assertEqual(self.portfolio["exhaustive_pareto_count"], 25)
        self.assertFalse(self.portfolio["flat_by_cap"][40]["options_match"])
        self.assertFalse(self.portfolio["flat_by_cap"][240]["options_match"])
        self.assertFalse(self.portfolio["flat_by_cap"][240]["pareto_match"])

        w3 = self.portfolio["factored_by_width"][3]
        self.assertTrue(w3["options_match"])
        self.assertTrue(w3["pareto_match"])
        self.assertEqual((w3["stage1_evaluations"], w3["stage2_evaluations"], w3["evaluations"]), (76, 244, 320))
        self.assertEqual((w3["model_calls"], w3["rounds"]), (33, 5))

    def test_factored_width_three_holds_under_pooled_company_budgets(self):
        for pool_usd, want_pareto in ((5050000.0, 20), (3500000.0, 19)):
            pooled = validate_org_scaling(COHORTS, budget_usd=pool_usd, widths=(3,), flat_caps=(40,))
            self.assertEqual(pooled["exhaustive_pareto_count"], want_pareto)
            self.assertTrue(pooled["factored_by_width"][3]["options_match"])
            self.assertTrue(pooled["factored_by_width"][3]["pareto_match"])

    def test_composable_cohort_front_matches_exhaustive_front_at_width_three(self):
        for org, fam in COHORTS:
            facts = cohort_facts(org, fam)
            beam_front = composable_cohort_front(search(facts, width=3)["nodes"])
            self.assertGreaterEqual(len(beam_front), 4)
            plan_run = plan_org_options([(org, fam)], width=3)
            self.assertEqual(len(plan_run["options"]), 3)


if __name__ == "__main__":
    unittest.main()
