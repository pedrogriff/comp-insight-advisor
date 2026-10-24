"""Unit tests for policy retrieval and the grounded options. Standard library only, no network."""

import json
from pathlib import Path
import re
import sys
import tempfile
import unittest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.retrieval.embeddings import HashingEmbedder, make_embedder  # noqa: E402
from src.retrieval.grounded_options import ground_options  # noqa: E402
from src.retrieval.policy_search import (PLAYBOOK_PATH, PolicyRetriever, check_limits, covers, evaluate,  # noqa: E402
                                         load_policy_chunks, save_scores, verify_rule)
from src.tools.interview_search import NoteIndex, load_notes  # noqa: E402


class ChunkingTest(unittest.TestCase):

    def test_rules_are_short_unique_and_tagged(self):
        chunks = load_policy_chunks()
        by_id = {c["id"]: c for c in chunks}
        self.assertEqual(len(chunks), 38)
        self.assertEqual(len(by_id), 38)
        self.assertLessEqual(max(len(c["text"].split()) for c in chunks if c["id"] != "6:table"), 140)
        self.assertEqual((by_id["2.1:thresholds"]["applies_to"], by_id["2.1:thresholds"]["levers"]),
                         ("new_hires", ["offer_band_review"]))
        self.assertEqual(by_id["6.2:lift"]["levers"], ["base_adjustment"])
        self.assertIn("0.95 compa-ratio", by_id["6.2:lift"]["text"])
        self.assertTrue(by_id["3:tier-0"]["search_text"].startswith("Section 3. The 4-Tier"))
        self.assertEqual([c["id"] for c in chunks if c["applies_to"] == "untagged"], [])

    def test_a_new_untagged_section_is_flagged(self):
        text = PLAYBOOK_PATH.read_text(encoding="utf-8") + "\n## Section 7. Relocation\n\n- **Allowance.** Up to 10000.\n"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "playbook.md"
            path.write_text(text, encoding="utf-8")
            added = [c for c in load_policy_chunks(path) if c["section"] == "7"]
        self.assertEqual([(c["id"], c["applies_to"], c["levers"]) for c in added], [("7:allowance", "untagged", [])])

    def test_every_rule_line_of_the_playbook_lands_in_a_chunk(self):
        text = PLAYBOOK_PATH.read_text(encoding="utf-8")
        spans = [c["span"] for c in load_policy_chunks()]
        start = text.index("## Section 1.")
        for m in re.finditer(r"^([ \t]*[-|]|[ \t]*\d+\.\s|[A-Z]).*$", text[start:], flags=re.M):
            pos = start + m.start()
            line = m.group(0)
            if line.startswith(("## ", "### ")) or line.rstrip().endswith(":"):
                continue
            self.assertTrue(any(a <= pos < b for a, b in spans), f"not in a chunk: {line[:60]}")

    def test_windows_cover_several_rules(self):
        rules = load_policy_chunks()
        windows = load_policy_chunks(strategy="windows")
        self.assertEqual(len(windows), 21)
        covered = [sum(covers(w, r) for r in rules) for w in windows]
        self.assertGreaterEqual(max(covered), 4)


class PolicySearchTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.retriever = PolicyRetriever()

    def test_unfiltered_search_surfaces_the_new_hire_near_miss(self):
        query = "Is there a compa-ratio cap for equity?"
        open_ids = [h["id"] for h in self.retriever.search(query, k=3)]
        kept = [h["id"] for h in self.retriever.search(query, k=3, filters={"levers": "retention_grant"})]
        self.assertEqual(open_ids[0], "2.1:thresholds")
        self.assertNotIn("2.1:thresholds", kept)
        self.assertEqual(self.retriever.search("lowest pay relative to market for current staff"), [])

    def test_lever_queries_return_the_governing_clauses(self):
        base = self.retriever.retrieve_for_lever("base_adjustment", ["Base_Salary_Cap"])
        self.assertEqual([h["id"] for h in base], ["6.2:lift", "6.2:floor", "6.2:eligibility"])
        self.assertTrue(all(c["ok"] for c in check_limits("base_adjustment", base)))
        level = self.retriever.retrieve_for_lever("level_review", ["Level_Up_Offer"])
        self.assertEqual([c["ok"] for c in check_limits("level_review", level)], [False])

    def test_verify_rule_blocks_the_checkpoint_2_1_cap(self):
        bad = verify_rule("Retention grants stop at a 1.20 post-grant compa-ratio cap.", "retention_grant", self.retriever)
        self.assertFalse(bad["ok"])
        self.assertIn("2.1:thresholds (new hires)", bad["problems"][0])
        good = verify_rule("Lifts stop at a 0.95 compa-ratio.", "base_adjustment", self.retriever, cited="6.2:lift")
        self.assertTrue(good["ok"])
        wrong = verify_rule("Lifts stop at a 1.00 compa-ratio.", "base_adjustment", self.retriever, cited="2.1:thresholds")
        self.assertEqual(wrong["problems"], ["2.1:thresholds governs offer_band_review, not base_adjustment"])

    def test_evaluation_matches_the_documented_baseline(self):
        dev, held = evaluate(split="dev")["configs"], evaluate(split="heldout")["configs"]
        self.assertEqual((dev["bm25 rules"]["hit_at_3"], dev["bm25 windows"]["hit_at_3"]), ("8/16", "8/16"))
        self.assertEqual((held["bm25 rules"]["hit_at_3"], held["bm25 windows"]["hit_at_3"]), ("3/8", "3/8"))
        self.assertEqual((dev["bm25 rules"]["mean_context_words"], dev["bm25 windows"]["mean_context_words"]), (58, 140))
        self.assertEqual((dev["bm25 rules"]["abstained_correctly"], held["bm25 rules"]["abstained_correctly"]),
                         ("2/2", "2/2"))
        # A lower bar looks better on the questions it was tuned on and no better on held-out ones.
        low_dev, low_held = dev["bm25 rules, floor 0.25"], held["bm25 rules, floor 0.25"]
        self.assertEqual((low_dev["hit_at_3"], low_held["hit_at_3"], low_held["abstained_correctly"]),
                         ("12/16", "3/8", "1/2"))
        self.assertEqual(held["bm25 rules + glossary"]["abstained_correctly"], "1/2")
        cases = json.loads((PROJECT_ROOT / "data" / "synthetic" / "policy_retrieval_cases.json").read_text())
        self.assertEqual([sum(c["split"] == s for c in cases) for s in ("dev", "heldout")], [18, 10])
        ids = {c["id"] for c in load_policy_chunks()}
        for case in cases:
            self.assertTrue(set(case["relevant"] + case["wrong_population"]) <= ids, case["case_id"])


class GroundedOptionsTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.notes = NoteIndex(load_notes())
        cls.with_rag = ground_options("VP_CLOUD_AI", "RESEARCH_SCI", PolicyRetriever(), cls.notes)
        cls.without = ground_options("VP_CLOUD_AI", "RESEARCH_SCI")

    def test_retrieval_backs_every_checklist_item(self):
        cited = {item["item"]: item["clause"]["id"] for item in self.with_rag["checklist"]}
        self.assertEqual(cited, {"default_lever_mismatch": "6.1:does-not", "thin_driver_evidence": "6.5:thin-evidence",
                                 "compa_floor_breach": "6.2:floor", "needs_calibration": "6.3:decision",
                                 "over_budget_base": "6.2:funding"})
        self.assertEqual(self.with_rag["unsupported"], 0)
        self.assertEqual([n["note_id"] for n in self.with_rag["exit_notes"]],
                         ["EXIT-0007", "EXIT-0020", "EXIT-0022", "EXIT-0024"])
        added = {lever: [c["id"] for c in hits if c["added_by"] == "limit_check"]
                 for lever, hits in self.with_rag["clauses"].items()}
        self.assertEqual(added["level_review"], ["6.3:candidates"])
        self.assertEqual(added["retention_grant"], ["3:tier-0"])

    def test_without_retrieval_the_same_costs_carry_no_policy(self):
        self.assertEqual(self.without["options"], self.with_rag["options"])
        self.assertEqual(self.without["unsupported"], 5)
        self.assertEqual(self.without["exit_notes"], [])
        self.assertTrue(all(not hits for hits in self.without["clauses"].values()))
        self.assertEqual([o["first_year_cost_usd"] for o in self.with_rag["options"]], [1524000.0, 2648000.0, 4006600.0])

    def test_a_changed_playbook_stops_the_stale_limit(self):
        text = PLAYBOOK_PATH.read_text(encoding="utf-8")
        self.assertIn("at most a `0.95` compa-ratio", text)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "playbook.md"
            path.write_text(text.replace("at most a `0.95` compa-ratio", "at most a `0.90` compa-ratio"), encoding="utf-8")
            changed = ground_options("VP_CLOUD_AI", "RESEARCH_SCI", PolicyRetriever(path=path), self.notes)
        self.assertEqual(len(changed["policy_conflicts"]), 1)
        self.assertIn("compa_lift_max = 0.95", changed["policy_conflicts"][0])

    def test_ai_ml_engineers_need_no_base_or_level_clauses(self):
        ctx = ground_options("VP_CLOUD_AI", "AI_ML_ENG", PolicyRetriever(), self.notes)
        self.assertEqual(sorted(ctx["clauses"]), ["offer_band_review", "retention_grant"])
        self.assertNotIn("default_lever_mismatch", [i["item"] for i in ctx["checklist"]])
        self.assertEqual(len(ctx["exit_notes"]), 7)


class SavedScoresTest(unittest.TestCase):

    def test_saved_scores_replay_the_embedder(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scores.json"
            live = HashingEmbedder(256)
            saved_data = save_scores(live, path)
            saved = make_embedder(f"saved:{path}")
            self.assertEqual(saved.name, "saved:hashing-256")
            self.assertEqual(len(saved_data["chunk_ids"]), 38)
            for split in ("dev", "heldout"):
                a, b = evaluate(live, split=split)["configs"], evaluate(saved, split=split)["configs"]
                for mode in ("dense", "hybrid"):
                    self.assertEqual(a[f"{mode} hashing-256"], b[f"{mode} saved:hashing-256"], (split, mode))
            run_live = ground_options("VP_CLOUD_AI", "RESEARCH_SCI", PolicyRetriever(live))
            run_saved = ground_options("VP_CLOUD_AI", "RESEARCH_SCI", PolicyRetriever(saved))
            self.assertEqual(run_live["clauses"], run_saved["clauses"])
            with self.assertRaises(KeyError):
                saved.embed(["a question nobody saved"], kind="query")
            changed = Path(tmp) / "playbook.md"
            changed.write_text(PLAYBOOK_PATH.read_text(encoding="utf-8").replace("0.95", "0.90"), encoding="utf-8")
            with self.assertRaises(ValueError):
                PolicyRetriever(saved, path=changed)


if __name__ == "__main__":
    unittest.main()
