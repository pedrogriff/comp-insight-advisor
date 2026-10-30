"""Unit tests for the cross-lever router. Standard library only, no network.

The checkpoint 3.1 graders asked how the agent answers "Compare the equity caps for new hires
versus current staff" without breaking its single-lever filters. These tests pin the plan,
the strict filters, the labeled merge, the comparison check and the measured results.
"""

import json
from pathlib import Path
import sys
import tempfile
import unittest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.retrieval.cross_lever import (CROSS_CASES_PATH, SHARED, evaluate_cross_lever, evaluate_routing,  # noqa: E402
                                       plan_question, router_queries, search_cross_lever, verify_comparison,
                                       writer_context)
from src.retrieval.embeddings import HashingEmbedder, make_embedder  # noqa: E402
from src.retrieval.hybrid_index import HybridIndex  # noqa: E402
from src.retrieval.policy_search import LEVER_QUERIES, PolicyRetriever, load_policy_chunks, save_scores  # noqa: E402

GRADERS = "Compare the equity caps for new hires versus current staff"
TRAP = "Is there a compa-ratio cap for equity?"
TWO_TOPICS = "Compare parental leave for new hires with retention grant tiers for current staff"
SAVED_ROUTER = PROJECT_ROOT / "experiments" / "policy_retrieval" / "nomic-embed-text-router.json"


class PlanTest(unittest.TestCase):

    def test_the_graders_question_becomes_two_filtered_sides(self):
        plan = plan_question(GRADERS)
        self.assertEqual(plan["route"], "split")
        self.assertEqual([(s["side"], s["query"]) for s in plan["sides"]],
                         [("new_hires/offer_band_review", "equity caps"),
                          ("current_employees/retention_grant", "equity caps")])
        self.assertEqual(plan["sides"][1]["boost"], LEVER_QUERIES["retention_grant"])

    def test_the_population_trap_gets_one_side_per_population_and_lever(self):
        plan = plan_question(TRAP)
        self.assertEqual([(s["side"], s["query"]) for s in plan["sides"]],
                         [("new_hires/offer_band_review", "compa-ratio cap equity"),
                          ("current_employees/retention_grant", "cap equity"),
                          ("current_employees/base_adjustment", "compa-ratio cap")])

    def test_each_side_keeps_its_own_clause_and_borrows_a_missing_topic(self):
        self.assertEqual([(s["side"], s["query"]) for s in plan_question(TWO_TOPICS)["sides"]],
                         [("new_hires/any", "parental leave"),
                          ("current_employees/retention_grant", "retention grant tiers")])
        flipped = plan_question("Compare retention grants for current staff versus new hires")
        self.assertEqual([(s["side"], s["query"]) for s in flipped["sides"]],
                         [("new_hires/offer_band_review", "equity"),
                          ("current_employees/retention_grant", "retention grants")])

    def test_one_side_runs_as_asked_and_no_cue_stays_open(self):
        question = "What can the Offers Desk approve on its own for a new hire?"
        single = plan_question(question)
        self.assertEqual((single["route"], single["sides"][0]["side"], single["sides"][0]["query"]),
                         ("single", "new_hires/offer_band_review", question))
        self.assertEqual(plan_question("How should the brief handle a cohort with only three departures?")["route"], "open")


class SearchTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.retriever = PolicyRetriever()
        cls.result = search_cross_lever(cls.retriever, GRADERS)

    def test_one_query_misses_both_limits_and_one_filter_drops_a_side(self):
        self.assertEqual([h["id"] for h in self.retriever.search(GRADERS, k=3)], ["6:table", "6:p1"])
        kept = self.retriever.search(GRADERS, k=3, filters={"levers": "retention_grant"})
        self.assertEqual([h["id"] for h in kept], ["6:table", "6:p1"])

    def test_each_side_finds_its_limit_inside_its_own_population(self):
        groups = {g["side"]: [c["id"] for c in g["clauses"]] for g in self.result["groups"]}
        self.assertEqual(groups, {"new_hires/offer_band_review": ["6.4:p1", "2.1:thresholds"],
                                  "current_employees/retention_grant": ["3:tier-1", "3:tier-3", "3:tier-2"]})
        self.assertEqual([c["id"] for c in self.result["shared"]], ["6:table"])
        for question in (GRADERS, TRAP, TWO_TOPICS):
            result = search_cross_lever(self.retriever, question)
            for group in result["groups"]:
                self.assertTrue(all(c["applies_to"] == group["population"] for c in group["clauses"]), question)
                self.assertTrue(all(group["lever"] in c["levers"] for c in group["clauses"] if group["lever"]), question)
            self.assertTrue(all(c["applies_to"] in SHARED for c in result["shared"]), question)

    def test_a_side_the_playbook_does_not_cover_stays_empty(self):
        result = search_cross_lever(self.retriever, TWO_TOPICS)
        self.assertEqual([(g["side"], g["status"]) for g in result["groups"]],
                         [("new_hires/any", "no_clause"), ("current_employees/retention_grant", "cited")])
        context = writer_context(result)
        self.assertIn("[New hires | any lever] No clause covers this side. Say so. Do not use another side's clause.",
                      context)
        self.assertIn("[Current employees | retention_grant] 3:tier-3: Tier 3: Max In-Range Ceiling", context)

    def test_boost_terms_rank_but_never_pass_the_gate(self):
        index = HybridIndex(load_policy_chunks())
        pool, boost = {"applies_to": "new_hires"}, LEVER_QUERIES["offer_band_review"]
        self.assertEqual(index.search("parental leave", mode="bm25", filters=pool, boost=boost), [])
        loose = index.search("parental leave", mode="bm25", filters=pool, boost=boost, min_coverage=0.0)
        self.assertEqual(loose[0]["id"], "6.4:p1")
        self.assertEqual(loose[0]["coverage"], 0.0)

    def test_a_single_population_question_keeps_the_keyword_gate_limit(self):
        # Known limit, kept on purpose: the design was frozen before the held-out run. One side
        # runs the question as asked, so "new hires" matches 2.1, as it does without the router.
        question = "What is the parental leave for new hires?"
        self.assertEqual([h["id"] for h in self.retriever.search(question, k=3)],
                         ["6.4:p1", "2.1:scope", "2.1:thresholds"])
        routed = search_cross_lever(self.retriever, question)
        self.assertEqual([c["id"] for c in routed["groups"][0]["clauses"]], ["6.4:p1", "2.1:scope", "2.1:thresholds"])

    def test_a_question_with_no_topic_sends_no_empty_query(self):
        # Saved scores hold no empty query, so an empty side or shared query must never be searched.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scores.json"
            save_scores(HashingEmbedder(256), path)
            saved = PolicyRetriever(make_embedder(f"saved:{path}"))
            result = search_cross_lever(saved, "Compare new hires and current staff")
        self.assertEqual([(g["side"], g["query"], g["status"]) for g in result["groups"]],
                         [("new_hires/any", "", "no_clause"), ("current_employees/any", "", "no_clause")])
        self.assertEqual((result["shared_query"], result["shared"]), ("", []))


class VerifyTest(unittest.TestCase):

    NEW = {"side": "new_hires/offer_band_review", "cited": "2.1:thresholds",
           "text": "New-hire offers up to 1.20x the equity guideline need only the Offers Desk."}
    CURRENT = {"side": "current_employees/retention_grant", "cited": "3:tier-3",
               "text": "Tier 3 grants reach 150% to 200% of the annual equity refresh guideline."}

    @classmethod
    def setUpClass(cls):
        cls.retriever = PolicyRetriever()
        cls.result = search_cross_lever(cls.retriever, GRADERS)

    def test_a_correct_comparison_passes(self):
        self.assertEqual(verify_comparison(self.result, [self.NEW, self.CURRENT], self.retriever),
                         {"ok": True, "problems": [], "missing_sides": []})

    def test_a_new_hire_limit_reported_for_current_staff_fails(self):
        swapped = {"side": "current_employees/retention_grant", "cited": "2.1:thresholds",
                   "text": "Current staff grants stop at 1.20x the equity guideline."}
        self.assertEqual(verify_comparison(self.result, [self.NEW, swapped], self.retriever)["problems"],
                         ["2.1:thresholds was not retrieved for current_employees/retention_grant",
                          "current_employees/retention_grant: 2.1:thresholds governs offer_band_review, not retention_grant"])
        uncited = {"side": "current_employees/retention_grant", "cited": None, "text": "Current staff equity is capped at 1.20x."}
        self.assertEqual(verify_comparison(self.result, [self.NEW, uncited], self.retriever)["problems"],
                         ["current_employees/retention_grant: 1.20 does not appear in a retention_grant clause. "
                          "It appears in 2.1:thresholds (new hires)"])

    def test_an_empty_side_cannot_borrow_a_rule_and_a_dropped_side_is_flagged(self):
        result = search_cross_lever(self.retriever, TWO_TOPICS)
        borrowed = {"side": "new_hires/any", "cited": "3:tier-1", "text": "New hires get 12 weeks of parental leave."}
        check = verify_comparison(result, [borrowed], self.retriever)
        self.assertEqual(check["problems"], ["No clause covers new_hires/any, so the brief must say so instead of stating a rule"])
        self.assertEqual(check["missing_sides"], ["current_employees/retention_grant"])
        self.assertEqual(verify_comparison(self.result, [self.NEW], self.retriever)["missing_sides"],
                         ["current_employees/retention_grant"])


class EvaluationTest(unittest.TestCase):
    """The router was tuned on the 5 dev questions only, then frozen, then scored once on held-out."""

    @classmethod
    def setUpClass(cls):
        cls.retriever = PolicyRetriever()

    def test_one_query_per_side_against_one_query(self):
        expected = {
            "dev": {"one query, no filter": ("3/9", "2/2", "1/5"), "one query, first side's filter": ("2/9", "2/2", "1/5"),
                    "one query per side": ("8/9", "2/2", "4/5")},
            "heldout": {"one query, no filter": ("0/11", "3/3", "1/7"), "one query, first side's filter": ("0/11", "3/3", "1/7"),
                        "one query per side": ("5/11", "3/3", "3/7")},
        }
        keys = ("sides_answered", "empty_sides_kept_empty", "questions_fully_right")
        for split, want in expected.items():
            configs = evaluate_cross_lever(self.retriever, split=split)["configs"]
            self.assertEqual({name: tuple(m[key] for key in keys) for name, m in configs.items()}, want, split)

    def test_routing_the_single_questions_costs_no_hit(self):
        for split, routes, hits, answerable in (("dev", {"open": 3, "single": 9, "split": 6}, 8, 16),
                                                ("heldout", {"open": 3, "single": 5, "split": 2}, 3, 8)):
            out = evaluate_routing(self.retriever, split=split)
            self.assertEqual((out["routes"], out["one_query_hits"], out["routed_hits"], out["answerable"]),
                             (routes, hits, hits, answerable), split)
            self.assertEqual((out["lost"], out["gained"], out["routed_abstained"], out["no_answer"]), ([], [], 2, 2), split)

    def test_the_cases_name_real_clauses_and_sides(self):
        cases = json.loads(CROSS_CASES_PATH.read_text(encoding="utf-8"))
        ids = {c["id"] for c in load_policy_chunks()}
        self.assertEqual([sum(c["split"] == s for c in cases) for s in ("dev", "heldout")], [5, 7])
        for case in cases:
            for key, relevant in case["sides"].items():
                pop, lever = key.split("/")
                self.assertIn(pop, ("new_hires", "current_employees"), case["case_id"])
                self.assertIn(lever, ("any", *LEVER_QUERIES), case["case_id"])
                self.assertTrue(set(relevant) <= ids, case["case_id"])
        self.assertIn("equity caps", router_queries())


class NomicRouterRunTest(unittest.TestCase):
    """Replays the router's nomic-embed-text scores, saved on Oct 30 on the personal machine, in hybrid mode.

    The held-out questions were scored once with the model, after the design froze on keyword search.
    """

    @classmethod
    def setUpClass(cls):
        cls.retriever = PolicyRetriever(make_embedder(f"saved:{SAVED_ROUTER}"))

    def test_hybrid_answers_more_sides_but_fills_two_empty_ones(self):
        self.assertEqual(self.retriever.mode, "hybrid")
        expected = {
            "dev": {"one query, no filter": ("5/9", "1/2", "0/5"), "one query, first side's filter": ("4/9", "1/2", "0/5"),
                    "one query per side": ("9/9", "2/2", "5/5")},
            "heldout": {"one query, no filter": ("5/11", "2/3", "2/7"), "one query, first side's filter": ("4/11", "1/3", "0/7"),
                        "one query per side": ("9/11", "1/3", "4/7")},
        }
        keys = ("sides_answered", "empty_sides_kept_empty", "questions_fully_right")
        for split, want in expected.items():
            configs = evaluate_cross_lever(self.retriever, split=split)["configs"]
            self.assertEqual({name: tuple(m[key] for key in keys) for name, m in configs.items()}, want, split)
        # Known limit: the playbook has no repricing rule, keyword search leaves both sides empty,
        # and dense similarity fills both.
        question = "How do stock option repricing rules differ for new hires and current staff?"
        filled = {g["side"]: [c["id"] for c in g["clauses"]] for g in search_cross_lever(self.retriever, question)["groups"]}
        self.assertEqual(filled, {"new_hires/offer_band_review": ["2.1:thresholds"],
                                  "current_employees/retention_grant": ["3:tier-1", "3:tier-2", "4:stale-promotion"]})
        self.assertTrue(all(g["status"] == "no_clause" for g in search_cross_lever(PolicyRetriever(), question)["groups"]))

    def test_routing_loses_two_dev_hits_and_gains_one_held_out(self):
        dev = evaluate_routing(self.retriever, split="dev")
        self.assertEqual((dev["one_query_hits"], dev["routed_hits"], dev["answerable"]), (16, 14, 16))
        self.assertEqual((dev["lost"], dev["gained"], dev["routed_abstained"], dev["no_answer"]), (["P12", "P16"], [], 2, 2))
        held = evaluate_routing(self.retriever, split="heldout")
        self.assertEqual((held["one_query_hits"], held["routed_hits"], held["answerable"]), (7, 8, 8))
        self.assertEqual((held["lost"], held["gained"], held["routed_abstained"], held["no_answer"]), ([], ["H3"], 1, 2))


if __name__ == "__main__":
    unittest.main()
