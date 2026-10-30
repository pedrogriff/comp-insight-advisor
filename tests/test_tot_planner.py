"""Unit tests for the Tree-of-Thought planner (checkpoint 4.1). Standard library only, no network."""

from pathlib import Path
import sys
import unittest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.planning.tot_planner import (ACTIONS, BEAM_WIDTH, MAX_DEPTH, choose_options, cohort_facts, compare,  # noqa: E402
                                      dominated, evaluate, every_plan, plan_options, search, template_audit)
from src.tools.intervention_fit import assess_intervention_fit  # noqa: E402

BASE = ("base_adjustment", "lift_to_0.95")
LEVEL = ("level_review", "promotion_low_case")
BAND = ("offer_band_review", "offers_desk")
TOP = ("retention_grant", "top_ceiling")


class TreeShapeTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.facts = cohort_facts("VP_CLOUD_AI", "RESEARCH_SCI")
        cls.tree = search(cls.facts)

    def test_six_actions_beam_three_depth_four(self):
        self.assertEqual(len(ACTIONS), 6)
        self.assertEqual((BEAM_WIDTH, MAX_DEPTH), (3, 4))
        self.assertEqual(sum(1 for n in self.tree["nodes"] if n["depth"] == 1), 6)
        self.assertEqual(max(n["depth"] for n in self.tree["nodes"]), 4)
        self.assertEqual(self.tree["evaluations"], 27)
        self.assertEqual(len(every_plan(self.facts)), 32)

    def test_two_paths_to_one_plan_are_evaluated_once(self):
        signatures = [n["signature"] for n in self.tree["nodes"]]
        self.assertEqual(len(signatures), len(set(signatures)))
        duplicates = [p for p in self.tree["pruned"] if p["reason"].startswith("duplicate")]
        self.assertEqual(len(duplicates), 7)

    def test_sizings_that_fund_the_same_people_take_one_beam_slot(self):
        self.assertEqual(self.facts["tiers"]["Tier_1"], 0)
        twins = [p for p in self.tree["pruned"] if p["reason"].startswith("same coverage")]
        self.assertEqual(len(twins), 1)
        self.assertIn("retention_grant:tier2_and_3", " ".join(f"{a}:{b}" for a, b in twins[0]["plan"]))


class CriticTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.facts = cohort_facts("VP_CLOUD_AI", "RESEARCH_SCI")

    def test_a_lift_and_a_promotion_for_one_employee_count_once(self):
        self.assertEqual(self.facts["lift_and_promotion"], 7)
        self.assertEqual(self.facts["joint_pricing_credit_usd"], 121800.0)
        alone = [evaluate(self.facts, (a,))["first_year_cost_usd"] for a in (BASE, LEVEL)]
        self.assertEqual(alone, [280600.0, 1078000.0])
        both = evaluate(self.facts, (BASE, LEVEL))
        self.assertEqual(both["first_year_cost_usd"], 280600.0 + 1078000.0 - 121800.0)

    def test_a_lever_with_no_eligible_employee_addresses_nothing(self):
        facts = cohort_facts("VP_CLOUD_AI", "SW_ENG")
        self.assertTrue(all(v["eligible"] == 0 for (lever, _), v in facts["actions"].items() if lever != "offer_band_review"))
        self.assertEqual(evaluate(facts, (TOP, LEVEL))["departures_addressed"], 0)
        template = assess_intervention_fit("VP_CLOUD_AI", "SW_ENG")["options"]
        self.assertEqual([(o["departures_addressed"], o["first_year_cost_usd"]) for o in template],
                         [(1, 0.0), (1, 0.0), (3, 0.0)])
        reasons = {p["reason"] for p in search(facts)["pruned"]}
        self.assertIn("no employee is eligible for retention_grant", reasons)

    def test_sign_offs_follow_the_playbook(self):
        full = evaluate(self.facts, tuple(sorted((BASE, LEVEL, BAND, TOP))))
        self.assertEqual(full["sign_offs"], ["VP, above the remaining proactive budget (Section 6.2)",
                                             "VP and Head of Compensation, Tier 3 grants (Section 3)",
                                             "Calibration committee, level decisions (Section 6.3)"])
        self.assertEqual(evaluate(self.facts, (BASE,))["sign_offs"], [])

    def test_a_plan_that_covers_no_more_and_costs_more_is_dominated(self):
        plans = {p["plan"]: p for p in every_plan(self.facts)}
        everything = list(plans.values())
        # Grants alone answer 1 departure for $1,524,000 and need Tier 3 sign-off. Base lifts answer
        # the same 1 departure for $280,600, and adding the free band review also covers 6 declined offers.
        self.assertTrue(dominated(plans[(TOP,)], everything))
        self.assertTrue(dominated(plans[(BASE,)], everything))
        self.assertFalse(dominated(plans[(BASE, BAND)], everything))


class OptionsTest(unittest.TestCase):

    def test_research_scientists_get_three_distinct_options(self):
        result = plan_options("VP_CLOUD_AI", "RESEARCH_SCI")
        got = [(o["role"], o["signature"], o["departures_addressed"], o["declined_addressed"], o["first_year_cost_usd"])
               for o in result["options"]]
        self.assertEqual(got, [
            ("most coverage inside the remaining budget",
             "base_adjustment:lift_to_0.95 + level_review:promotion_low_case + offer_band_review:offers_desk", 3, 6, 1236800.0),
            ("most coverage at any cost",
             "base_adjustment:lift_to_0.95 + level_review:promotion_low_case + offer_band_review:offers_desk"
             " + retention_grant:top_ceiling", 4, 6, 2760800.0),
            ("cheapest plan that answers at least half of the departures",
             "level_review:promotion_low_case + offer_band_review:offers_desk", 2, 6, 1078000.0),
        ])
        self.assertEqual(result["options"][1]["budget_gap_usd"], 610800.0)
        self.assertEqual(len({o["signature"] for o in choose_options(result)}), 3)


class ComparisonTest(unittest.TestCase):
    """The three cohorts that pass the evidence check, CONVERGENT, which are the ones that reach options."""

    @classmethod
    def setUpClass(cls):
        cls.rows = {r["scope"]: r for r in compare()}

    def test_a_chain_that_commits_to_grants_first_misses_where_drivers_point_elsewhere(self):
        def inside(r, name):
            e = r[name]
            return (e["departures_addressed"], e["first_year_cost_usd"])
        expect = {
            "VP_CLOUD_AI RESEARCH_SCI": {"grant_first": (2, 1804600.0), "greedy": (3, 1236800.0),
                                         "beam": (3, 1236800.0), "full": (3, 1236800.0)},
            "VP_CLOUD_AI AI_ML_ENG": {"grant_first": (7, 2009200.0), "greedy": (7, 2009200.0),
                                      "beam": (7, 2009200.0), "full": (7, 2009200.0)},
            "VP_SEC_INTEL CYBER_SEC_ENG": {"grant_first": (4, 2574400.0), "greedy": (4, 2574400.0),
                                           "beam": (4, 2574400.0), "full": (4, 2574400.0)},
        }
        for scope, want in expect.items():
            self.assertEqual({name: inside(self.rows[scope], name) for name in want}, want, scope)

    def test_templates_do_worse_and_repeat_themselves(self):
        templates = {s: (r["template"]["option"], r["template"]["departures_addressed"], r["template"]["first_year_cost_usd"],
                         r["template_repeats"]) for s, r in self.rows.items()}
        self.assertEqual(templates, {"VP_CLOUD_AI RESEARCH_SCI": ("A", 1, 1524000.0, 0),
                                     "VP_CLOUD_AI AI_ML_ENG": ("A", 6, 1715000.0, 1),
                                     "VP_SEC_INTEL CYBER_SEC_ENG": ("A", 3, 2142000.0, 1)})

    def test_what_each_search_costs(self):
        evaluations = {s: (r["grant_first_evaluations"], r["greedy_evaluations"], r["beam_evaluations"], r["full_plans"])
                       for s, r in self.rows.items()}
        self.assertEqual(evaluations, {"VP_CLOUD_AI RESEARCH_SCI": (7, 18, 27, 32),
                                       "VP_CLOUD_AI AI_ML_ENG": (7, 12, 24, 32),
                                       "VP_SEC_INTEL CYBER_SEC_ENG": (7, 12, 25, 32)})

    def test_templates_claim_departures_for_nothing_where_nobody_is_eligible(self):
        rows = template_audit()
        free = [r for r in rows if r["free_claims"]]
        self.assertEqual((len(rows), len(free)), (13, 8))
        # The evidence check stops all 8 today, so the claims never reach a brief. The critic stops them anyway.
        self.assertEqual([r["pattern"] for r in free], ["NO_SIGNAL"] * 8)


if __name__ == "__main__":
    unittest.main()
