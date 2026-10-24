"""Unit tests for the interview notes generator and the lexical retrieval baseline."""

from contextlib import closing
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.tools.interview_search import CASES_PATH, NOTES_PATH, NoteIndex, evaluate, load_notes, tokenize

DATA_DIR = PROJECT_ROOT / "data" / "synthetic"
DRIVERS = ("Total_Equity_Size", "Cashflow_Year1_Gap", "Base_Salary_Cap", "Level_Up_Offer")


def _generator():
    spec = importlib.util.spec_from_file_location("generate_interview_notes", DATA_DIR / "generate_interview_notes.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _note(note_id: str, text: str, themes: list[str], org: str = "VP_A", note_type: str = "exit") -> dict:
    return {"note_id": note_id, "note_type": note_type, "vp_org_code": org, "job_family": "FAM",
            "themes": themes, "text": text}


class SearchTest(unittest.TestCase):

    def test_tokenize_lowercases_strips_plurals_and_stopwords(self) -> None:
        self.assertEqual(tokenize("The Grants were Bigger"), ["grant", "bigger"])
        self.assertEqual(tokenize("policies and RSUs"), ["policy", "rsu"])

    def test_filters_limit_results(self) -> None:
        index = NoteIndex([_note("N1", "My stock grant was small.", ["Total_Equity_Size"], org="VP_A"),
                           _note("N2", "My stock grant was small.", ["Total_Equity_Size"], org="VP_B")])
        hits = index.search("stock grant", filters={"vp_org_code": "VP_B"})
        self.assertEqual([h["note_id"] for h in hits], ["N2"])

    def test_expansion_finds_a_paraphrase_plain_search_misses(self) -> None:
        index = NoteIndex([_note("N1", "My fixed pay sat below what others earn.", ["Base_Salary_Cap"])])
        self.assertEqual(index.search("salary raise", expand=False), [])
        self.assertEqual([h["note_id"] for h in index.search("salary raise", expand=True)], ["N1"])

    def test_coverage_floor_returns_nothing_for_an_unanswered_question(self) -> None:
        index = NoteIndex([_note("N1", "The new return-to-office policy did not work for my family.", ["remote_policy"])])
        self.assertEqual(index.search("parental leave policy complaints"), [])

    def test_mmr_skips_near_duplicates(self) -> None:
        index = NoteIndex([
            _note("D1", "The stock grant elsewhere was much larger.", ["Total_Equity_Size"]),
            _note("D2", "The stock grant elsewhere was much larger, honestly.", ["Total_Equity_Size"]),
            _note("D3", "The stock grant elsewhere was much larger overall.", ["Total_Equity_Size"]),
            _note("X1", "My stock grant was fine, but my promotion stalled for two cycles.", ["Level_Up_Offer"]),
        ])
        plain = [h["note_id"] for h in index.search("stock grant", k=2)]
        diverse = [h["note_id"] for h in index.search("stock grant", k=2, use_mmr=True)]
        self.assertNotIn("X1", plain)
        self.assertIn("X1", diverse)
        self.assertEqual(index.near_duplicates(plain), 1)
        self.assertEqual(index.near_duplicates(diverse), 0)

    def test_empty_query_with_filters_is_a_metadata_lookup(self) -> None:
        index = NoteIndex([_note(f"N{i}", f"Note number {i}.", ["stay_team"], note_type="stay") for i in range(3)]
                          + [_note("E1", "Exit note.", ["Base_Salary_Cap"])])
        hits = index.search("", k=2, filters={"note_type": "stay"})
        self.assertEqual([h["note_id"] for h in hits], ["N0", "N1"])
        self.assertEqual(index.search(""), [])

    def test_search_many_gives_each_part_of_a_question_a_match(self) -> None:
        index = NoteIndex([
            _note("S1", "My salary is below market.", ["Base_Salary_Cap"]),
            _note("S2", "I need a promotion within a year.", ["Level_Up_Offer"]),
        ])
        self.assertEqual(index.search("salary promotion concerns", k=5), [])
        merged = {h["note_id"] for h in index.search_many(["salary", "promotion"], k=5)}
        self.assertEqual(merged, {"S1", "S2"})


class CorpusTest(unittest.TestCase):

    def test_generator_is_deterministic_and_the_committed_files_are_current(self) -> None:
        gen = _generator()
        with tempfile.TemporaryDirectory() as tmp:
            notes, cases = Path(tmp) / "notes.jsonl", Path(tmp) / "cases.json"
            gen.generate(DATA_DIR / "comp_insight_advisor.db", notes, cases)
            self.assertEqual(notes.read_bytes(), NOTES_PATH.read_bytes())
            self.assertEqual(cases.read_bytes(), CASES_PATH.read_bytes())

    def test_exit_notes_follow_the_offers_log(self) -> None:
        notes = load_notes()
        counts = {}
        for note in notes:
            counts[note["note_type"]] = counts.get(note["note_type"], 0) + 1
        self.assertEqual(counts, {"exit": 36, "stay": 90, "proactive_stay": 135})
        with closing(sqlite3.connect(DATA_DIR / "comp_insight_advisor.db")) as conn:
            drivers = dict(conn.execute(
                "SELECT event_id, primary_loss_driver FROM reactive_offers_counters"
                " WHERE event_type = 'Reactive_Counter_Offer' AND outcome = 'Declined_Lost'"))
        exits = [n for n in notes if n["note_type"] == "exit"]
        self.assertEqual(sorted(n["source_event_id"] for n in exits), sorted(drivers))
        for note in exits:
            self.assertEqual(note["themes"][0], drivers[note["source_event_id"]])

    def test_note_text_never_names_a_driver_code(self) -> None:
        for note in load_notes():
            for code in DRIVERS:
                self.assertNotIn(code, note["text"])


class EvaluationTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.report = {row["case_id"]: row for row in evaluate()["cases"]}

    def test_filters_return_every_exit_note_for_the_cohort(self) -> None:
        self.assertEqual(self.report["R1"]["expanded"]["precision_at_k"], 1.0)
        self.assertEqual(self.report["R1"]["expanded"]["recall_at_10"], 1.0)

    def test_expansion_raises_recall_on_paraphrased_equity_notes(self) -> None:
        for case in ("R5", "R10"):
            self.assertGreater(self.report[case]["expanded"]["recall_at_10"], self.report[case]["plain"]["recall_at_10"])

    def test_mmr_widens_broad_questions(self) -> None:
        for case in ("R6", "R7"):
            self.assertGreater(self.report[case]["expanded_mmr"]["distinct_themes_at_k"],
                               self.report[case]["expanded"]["distinct_themes_at_k"])

    def test_a_mixed_question_needs_sub_queries(self) -> None:
        cases = {c["case_id"]: c for c in json.loads(CASES_PATH.read_text(encoding="utf-8"))}
        r7 = cases["R7"]
        index = NoteIndex(load_notes())
        single = index.search(r7["search_query"], filters=r7["filters"])
        split = index.search_many(r7["sub_queries"], filters=r7["filters"])
        self.assertLess(len(single), 5)
        self.assertEqual(len(split), 5)

    def test_unanswered_question_returns_nothing_in_every_setup(self) -> None:
        for config in ("plain", "expanded", "expanded_mmr"):
            self.assertTrue(self.report["R9"][config]["abstained"])


if __name__ == "__main__":
    unittest.main()
