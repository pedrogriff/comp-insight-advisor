"""Tests for the final evaluation: the scorecard, the model fact check and the live writer check.

No test here reaches a model. A fake transport plays the model, so each test names exactly what
the model wrote and checks what the advisor did with it. The one run recorded with a real model is
read from its file, and its drafts are checked again against today's checks.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

from src.agents.coordinator import MultiAgentCoordinator
from src.agents.state import deterministic_verify_brief, numbers_in
from src.evaluation import live_writer, scorecard
from src.guardrails.evaluate import FAULTS
from src.guardrails.output_guard import check_model_prose
from src.guardrails.pipeline import AWAITING_APPROVAL, RELEASED, GuardedAdvisor
from src.models.router import (
    GEMINI_FAST_MODEL,
    MODEL_ATTEMPTS,
    OUTCOME_AFTER_ERROR,
    OUTCOME_AFTER_REJECTION,
    OUTCOME_MODEL,
    OUTCOME_REJECTED,
    ModelRouter,
)

# The blank overrides keep a model name exported in the shell out of these tests.
KEY = {"OPENROUTER_API_KEY": "sk-or-test-real-key", "ADVISOR_REASONING_MODEL": "", "ADVISOR_FAST_MODEL": ""}
POLICY_QUESTION = "Compare the equity caps for new hires versus current staff."
faithful, inventing = live_writer.stand_in_copies, live_writer.stand_in_invents


def _facts(payload: dict) -> str:
    return payload["messages"][1]["content"]


def repairing(url: str, headers: dict, payload: dict, timeout_s: float) -> dict:
    """Adds a percentage on the first try and drops it once the prompt reports the rejection."""
    text = live_writer._code_written_summary(payload)
    if "failed deterministic verification" not in _facts(payload):
        text += " Win rate rises to 12.3%."
    return live_writer._reply(text)


def promising(url: str, headers: dict, payload: dict, timeout_s: float) -> dict:
    return live_writer._reply(live_writer._code_written_summary(payload) + " This plan guarantees retention.")


def unreachable(url: str, headers: dict, payload: dict, timeout_s: float) -> dict:
    raise urllib.error.URLError("no route to host")


class ScorecardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.card = scorecard.build()
        cls.committed = json.loads(scorecard.JSON_PATH.read_text(encoding="utf-8"))

    def test_committed_scorecard_matches_the_code(self) -> None:
        self.assertEqual(scorecard.differences(scorecard.stable(self.committed), scorecard.stable(self.card)), [])
        self.assertNotIn("timing", scorecard.stable(self.card))

    def test_committed_markdown_comes_from_the_committed_json(self) -> None:
        self.assertEqual(scorecard.MD_PATH.read_text(encoding="utf-8"), scorecard.render_markdown(self.committed))

    def test_results_the_final_report_quotes(self) -> None:
        card = self.card
        counting = card["model_alone"]["counting"]
        self.assertEqual(counting["right_answer"], [87, 24])
        self.assertEqual((counting["reading_the_rows"]["right"], counting["reading_the_rows"]["runs"]), (0, 5))
        self.assertEqual(counting["reading_the_rows"]["answers"],
                         [[125, 25], [111, 23], [144, 33], [135, 23], [142, 25]])
        self.assertEqual((counting["reading_the_tool_summary"]["right"],
                          counting["reading_the_tool_summary"]["runs"]), (5, 5))
        dividing = card["model_alone"]["dividing"]
        self.assertEqual((dividing["in_text"]["exact_median"], dividing["with_a_divide_tool"]["exact_median"],
                          dividing["employees"]), (297, 300, 300))

        squad = card["one_agent_or_squad"]
        self.assertEqual((squad["one_agent"]["cost_usd"], squad["squad"]["cost_usd"], squad["budget_usd"]),
                         (3246000, 1995600, 2150000))

        policy = card["retrieval"]["policy_questions"]
        self.assertEqual([policy[mode]["right_clause_in_top_3"]["all"] for mode in ("keyword", "dense", "hybrid")],
                         ["11/24", "24/24", "23/24"])
        self.assertEqual([policy[mode]["returned_nothing_when_uncovered"]["all"]
                          for mode in ("keyword", "dense", "hybrid")], ["4/4", "3/4", "3/4"])
        held_out = {mode: card["retrieval"]["cross_lever_comparisons"][mode]["held_out"]
                    for mode in ("keyword", "hybrid")}
        self.assertEqual(
            [held_out[mode][config]["sides_answered"] for mode in ("keyword", "hybrid")
             for config in ("one_query", "one_query_per_side")],
            ["0/11", "5/11", "5/11", "9/11"],
        )

        plan = card["planning"]
        width_3 = plan["by_beam_width"]["3"]
        self.assertEqual((width_3["options_right"], width_3["options"], width_3["pareto_plans_missed"],
                          width_3["budget_levels_wrong"], width_3["budget_levels"]), (9, 9, 0, 0, 105))
        self.assertEqual((width_3["critic_reviews"], plan["exhaustive"]["critic_reviews"],
                          plan["fewer_critic_reviews_at_width_3_pct"]), (30, 93, 67.7))
        self.assertGreater(plan["by_beam_width"]["1"]["budget_levels_wrong"], 0)

        guard = card["guardrails"]
        self.assertEqual((guard["request_screen"]["all_splits"]["false_refusals"],
                          guard["request_screen"]["all_splits"]["benign"]), (0, 50))
        self.assertEqual((guard["containment"]["contained"], guard["containment"]["violations_past_the_screen"]),
                         (10, 10))
        check = guard["verifier_and_output_check"]
        self.assertEqual((check["faults_rejected"], check["faults_seeded"], len(FAULTS)), (158, 163, 15))
        self.assertEqual((card["routing"]["requests"], card["routing"]["released_without_a_person"],
                          card["routing"]["waited_for_a_person"], card["routing"]["held"]), (23, 18, 5, 0))
        self.assertEqual(card["routing"]["what_sent_briefs_to_a_person"], {
            "costed_options": 5, "ledger_reconciliation_flag": 5, "tier3_grant": 5, "level_decision": 4,
            "over_remaining_budget": 4, "thin_evidence": 2})
        shared = guard["shared_state"]
        self.assertEqual((shared["final_states_naming_an_employee"], shared["runs"],
                          shared["stores_naming_an_employee"], len(shared["stores_checked"])), (0, 23, [], 3))
        self.assertEqual((guard["runtime_monitor"]["trace_faults_flagged"],
                          guard["runtime_monitor"]["trace_faults_seeded"]), (8, 8))

        prose = card["model_prose"]
        self.assertEqual((prose["copies_the_facts"]["first_draft_accepted"], prose["copies_the_facts"]["runs"]),
                         (23, 23))
        invents = prose["invents_a_figure"]
        self.assertEqual((invents["ended_on_the_code_written_paragraph"], invents["not_verified"],
                          invents["same_route_as_the_code_written_run"], invents["first_draft_accepted"]),
                         (23, 0, 23, 0))

        live = prose["recorded_run"]
        self.assertEqual((live["model"], live["recorded_on"], live["runs"], live["model_calls"]),
                         ("gemini-3.5-flash-lite", "2026-11-18", 23, 24))
        self.assertEqual((live["first_draft_accepted"], live["redraft_accepted"],
                          live["ended_on_the_code_written_paragraph"], live["model_errors"], live["not_verified"],
                          live["same_route_as_the_code_written_run"]), (22, 1, 0, 0, 0, 23))
        self.assertEqual(live["drafts_rejected_by_kind"], {"unsupported_certainty": 1})
        self.assertEqual(live["replay"], {"accepted_drafts": 23, "still_pass": 23, "rejected_drafts": 1,
                                          "still_fail": 1, "changed": []})

    def test_quotable_figures_come_from_the_headline(self) -> None:
        self.assertEqual(scorecard.figures("at $3,246,000, $1,096,000 over; 85 of 1,024 plans, 67.7% fewer."),
                         {"$3,246,000", "$1,096,000", "85 of 1,024", "67.7%"})
        quotable = scorecard.quotable(self.card)
        for figure in ("0 of 5", "297 of 300", "$1,995,600", "24 of 24", "9 of 11", "105 of 105", "67.7%",
                       "0 of 50", "40 of 48", "10 of 10", "158 of 163", "9 of 9", "5 of 23", "18 of 23", "21.7%",
                       "8 of 8", "0 of 3", "5 of 5", "22 of 23", "1 of 23", "1 of 1"):
            self.assertIn(figure, quotable)

    def test_answer_numbers_skip_percentages_names_and_decimals(self) -> None:
        find = scorecard._ANSWER_INT.findall
        self.assertEqual(find("125 employees face a drop of 15% or more, and 25 of those are rating_4 or rating_5 "
                              "(yoy_cashflow_change_26_to_27_pct <= -15.0)."), ["125", "25"])
        self.assertEqual(find("87 and 24."), ["87", "24"])
        self.assertEqual(find("87, 24\r\r\nHow I got them: cliff_count_gt_15pct (87)"), ["87", "24", "87"])

    def test_differences_name_the_path(self) -> None:
        self.assertEqual(scorecard.differences({"a": {"b": 1, "c": 2}}, {"a": {"b": 1, "c": 3}}),
                         ["a.c: committed 2, now 3"])
        self.assertEqual(scorecard.differences({"a": 1}, {"a": 1, "b": 2}), ["b: only in the new scorecard"])


class FactCheckTests(unittest.TestCase):
    FACTS = ("Headline: 87 cliff cases across 500 employees. Option 1 (most coverage inside the budget): 7 of 11 "
             "departures for $1,995,600 under a $2,150,000 budget. Equity guideline 1.20x. Cited: 6.2:floor.")

    def test_numbers_read_as_values(self) -> None:
        self.assertEqual(sorted(numbers_in("Q1 plan: $1,995,600 at 1.20x for rating_4, 7 of 11, v2, 0.95.")),
                         [0.95, 1.2, 7.0, 11.0, 1995600.0])
        self.assertEqual(numbers_in("1,2 and 3.")[1.0], "1")

    def test_rewording_passes_and_a_new_number_fails(self) -> None:
        self.assertEqual(check_model_prose("Option 1 costs $1,995,600 and addresses 7 of 11 departures, "
                                           "inside the $2,150,000 budget at a 1.2x guideline.", self.FACTS), ())
        for text, token in (("The plan costs about $2.0 million.", "2.0"),
                            ("It covers 8 of 11 departures.", "8"),
                            ("Roughly 120 employees are affected.", "120"),
                            ("Win rate rises to 87.5%.", "87.5")):
            issues = check_model_prose(text, self.FACTS)
            self.assertEqual(len(issues), 1, text)
            self.assertTrue(issues[0].startswith(f"new_figure: the model wrote {token},"), issues)

    def test_forbidden_claims_fail_without_any_number(self) -> None:
        kinds = [issue.split(":")[0] for issue in check_model_prose(
            "The VP has approved Option 1, and this plan guarantees retention for EMP10254.", self.FACTS)]
        self.assertEqual(sorted(kinds), ["decision_claim", "employee_identifier", "unsupported_certainty"])

    def test_policy_answer_with_an_invented_figure_is_rejected_by_the_reviewer(self) -> None:
        coordinator = MultiAgentCoordinator()
        clean = coordinator.run(POLICY_QUESTION, thread_id="policy-clean")
        self.assertEqual(clean.status, "APPROVED")
        verdict = deterministic_verify_brief(FAULTS["invented_policy_figure"](clean), coordinator.policy)
        self.assertFalse(verdict.approved)
        self.assertEqual([issue.split(":")[0] for issue in verdict.issues], ["unverified_policy_figure"])
        self.assertIn("9,999,999", verdict.issues[0])


class RouterFactCheckTests(unittest.TestCase):
    def _advisor(self, transport, tmp: str) -> tuple[GuardedAdvisor, ModelRouter]:
        router = ModelRouter(provider="openrouter", env_path=None, transport=transport)
        return GuardedAdvisor(runtime_dir=tmp, writer_fn=router.make_writer()), router

    def test_two_rejected_tries_end_on_the_code_written_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, KEY):
            advisor, router = self._advisor(inventing, tmp)
            result = advisor.run("Prepare the Q1 retention brief for VP_CLOUD_AI.", "VP_CLOUD_AI")
            self.assertEqual(result.status, AWAITING_APPROVAL)
            self.assertEqual(result.state.revisions, 0)
            self.assertNotIn("9,999,999", result.brief)
            self.assertEqual([call.outcome for call in router.call_log],
                             [OUTCOME_REJECTED] * MODEL_ATTEMPTS + [OUTCOME_AFTER_REJECTION])
            self.assertTrue(router.call_log[0].problems[0].startswith("new_figure: the model wrote 9,999,999"))
            self.assertTrue(router.call_log[-1].used_fallback)

    def test_a_rejected_try_is_reported_to_the_model_and_the_repair_is_used(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, KEY):
            advisor, router = self._advisor(repairing, tmp)
            result = advisor.run("Prepare the Q1 retention brief for VP_CLOUD_AI.", "VP_CLOUD_AI")
            self.assertEqual(result.status, AWAITING_APPROVAL)
            self.assertEqual([call.outcome for call in router.call_log], [OUTCOME_REJECTED, OUTCOME_MODEL])
            self.assertNotIn("12.3%", result.brief)

    def test_policy_answer_never_carries_a_model_figure_to_auto_release(self) -> None:
        # Before this check, the reviewer skipped the prose of a policy answer, and policy answers are
        # released without a person.
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, KEY):
            advisor, router = self._advisor(inventing, tmp)
            result = advisor.run(POLICY_QUESTION)
            self.assertEqual(result.status, RELEASED)
            self.assertNotIn("9,999,999", result.brief)
            self.assertEqual(router.call_log[-1].outcome, OUTCOME_AFTER_REJECTION)

    def test_a_promise_costs_a_retry_not_a_held_brief(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, KEY):
            advisor, router = self._advisor(promising, tmp)
            result = advisor.run("Prepare the Q1 retention brief for VP_CLOUD_AI.", "VP_CLOUD_AI")
            self.assertEqual(result.status, AWAITING_APPROVAL)
            self.assertNotIn("guarantees", result.brief)
            self.assertEqual(router.call_log[0].problems[0].split(":")[0], "unsupported_certainty")

    def test_model_names_can_come_from_the_environment(self) -> None:
        seen: list[str] = []

        def recording(url: str, headers: dict, payload: dict, timeout_s: float) -> dict:
            seen.append(payload["model"])
            return faithful(url, headers, payload, timeout_s)

        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ, {**KEY, "ADVISOR_REASONING_MODEL": "vendor/newer-model"}
        ):
            advisor, router = self._advisor(recording, tmp)
            self.assertEqual(router.model_for_role("executive_synthesizer", "gemini"), "vendor/newer-model")
            self.assertEqual(router.model_for_role("supervisor", "gemini"), GEMINI_FAST_MODEL)
            self.assertEqual(router.model_for_role("executive_synthesizer", "offline"), "deterministic-reasoning")
            advisor.run("Prepare the Q1 retention brief for VP_CLOUD_AI.", "VP_CLOUD_AI")
            self.assertEqual(seen, ["vendor/newer-model"])
            self.assertEqual(router.call_log[-1].model, "vendor/newer-model")

    def test_provider_errors_and_empty_replies_say_why(self) -> None:
        def says(reply) -> str:
            with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, KEY):
                advisor, router = self._advisor(lambda url, headers, payload, timeout_s: reply, tmp)
                result = advisor.run("Prepare the Q1 retention brief for VP_CLOUD_AI.", "VP_CLOUD_AI")
                self.assertEqual(result.status, AWAITING_APPROVAL)
                self.assertEqual(router.call_log[-1].outcome, OUTCOME_AFTER_ERROR)
                return router.call_log[-1].note

        self.assertIn("the provider answered with an error: No endpoints found for this model",
                      says({"error": {"message": "No endpoints found for this model", "code": 404}}))
        self.assertIn("empty summary (finish reason: length)",
                      says({"choices": [{"finish_reason": "length", "message": {"content": None}}]}))
        self.assertIn("empty summary (finish reason: not given)", says({"choices": []}))
        self.assertIn("not a JSON object", says(["unexpected"]))
        # A reply in content parts still reads as text.
        self.assertEqual(ModelRouter._reply_text(
            {"choices": [{"message": {"content": [{"type": "text", "text": "Two cohorts."}]}}]}), "Two cohorts.")
        self.assertEqual(ModelRouter._reply_text({"message": {"content": " Local reply. "}, "done_reason": "stop"}),
                         "Local reply.")

    def test_an_http_error_carries_the_providers_words(self) -> None:
        error = urllib.error.HTTPError(
            "https://example.invalid/v1/chat/completions", 404, "Not Found", None,
            io.BytesIO(b'{"error": {"message": "model vendor/retired-model\n   is not available"}}'))
        with patch("urllib.request.urlopen", side_effect=error), self.assertRaises(RuntimeError) as caught:
            ModelRouter._http_json_post("https://example.invalid/v1/chat/completions", {}, {"model": "x"}, 1.0)
        self.assertEqual(str(caught.exception), 'HTTP 404 from the provider: {"error": {"message": '
                                                '"model vendor/retired-model is not available"}}')


class RecordedRunTests(unittest.TestCase):
    """The run saved on Nov 18, 2026 with a real model writing the summary. No model runs here."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.saved = json.loads(scorecard.RECORDED_RUN.read_text(encoding="utf-8"))

    def test_saved_summary_comes_from_its_own_rows(self) -> None:
        self.assertEqual(live_writer.summarize(self.saved["runs"]), self.saved["summary"])
        self.assertEqual((self.saved["provider"], self.saved["repeats"], len(self.saved["runs"])), ("gemini", 1, 23))
        self.assertEqual({row["kind"] for row in self.saved["runs"]}, set(live_writer.KINDS))

    def test_the_one_rejected_draft_promised_an_outcome_and_the_redraft_did_not(self) -> None:
        redrafted = [row for row in self.saved["runs"] if row["ended_with"] == "model_redraft"]
        self.assertEqual(len(redrafted), 1)
        first, second = redrafted[0]["drafts"]
        self.assertEqual((first["by"], second["by"]), (OUTCOME_REJECTED, OUTCOME_MODEL))
        self.assertEqual([issue.split(":")[0] for issue in first["rejected_for"]], ["unsupported_certainty"])
        self.assertIn("guaranteed", first["text"])
        self.assertNotRegex(second["text"], "(?i)guarantee")
        self.assertTrue(redrafted[0]["verified"] and redrafted[0]["same_end_as_code_written"])

    def test_replayed_today_accepted_drafts_pass_and_the_rejected_draft_fails(self) -> None:
        self.assertEqual(live_writer.reverify(self.saved), {
            "accepted_checked": 23, "accepted_still_pass": 23, "rejected_checked": 1, "rejected_still_fail": 1,
            "changed": []})

    def test_a_draft_changed_after_the_fact_is_caught_by_the_replay(self) -> None:
        tampered = json.loads(json.dumps(self.saved))
        tampered["runs"][0]["drafts"][-1]["text"] += " A further $9,999,999 sits in reserve."
        check = live_writer.reverify(tampered)
        self.assertEqual((check["accepted_still_pass"], len(check["changed"])), (22, 1))


class LiveWriterTests(unittest.TestCase):
    def _run(self, transport, **kwargs) -> dict:
        with patch.dict(os.environ, KEY):
            return live_writer.run("openrouter", transport=transport, env_path=None, **kwargs)

    def test_a_faithful_model_ends_every_run_on_its_first_draft(self) -> None:
        result = self._run(faithful)
        summary = result["summary"]
        self.assertEqual((summary["runs"], summary["requests"], summary["model_calls"]), (23, 23, 23))
        self.assertEqual((summary["model_first_draft_verified"], summary["same_end_as_code_written"]), (23, 23))
        self.assertEqual({row["kind"] for row in result["runs"]}, set(live_writer.KINDS))
        self.assertEqual(live_writer.reverify(result), {
            "accepted_checked": 23, "accepted_still_pass": 23, "rejected_checked": 0, "rejected_still_fail": 0,
            "changed": []})
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertTrue(live_writer.print_summary(result))
        self.assertIn("LIVE WRITER OK", out.getvalue())

    def test_an_inventing_model_never_changes_where_a_run_ends(self) -> None:
        result = self._run(inventing, only=("org_brief", "policy_question"))
        summary = result["summary"]
        self.assertEqual((summary["runs"], summary["model_calls"]), (7, 7 * MODEL_ATTEMPTS))
        self.assertEqual((summary["code_written_after_rejection"], summary["not_verified"],
                          summary["same_end_as_code_written"]), (7, 0, 7))
        self.assertEqual(summary["rejected_issue_kinds"], {"new_figure": 14})
        for row in result["runs"]:
            self.assertEqual([draft["by"] for draft in row["drafts"]],
                             [OUTCOME_REJECTED, OUTCOME_REJECTED, OUTCOME_AFTER_REJECTION])
        check = live_writer.reverify(result)
        self.assertEqual((check["rejected_checked"], check["rejected_still_fail"], check["changed"]), (14, 14, []))

    def test_a_repairing_model_ends_on_its_redraft(self) -> None:
        result = self._run(repairing, only=("org_brief",), repeats=2)
        summary = result["summary"]
        self.assertEqual((summary["runs"], summary["requests"]), (8, 4))
        self.assertEqual((summary["model_redraft_verified"], summary["model_first_draft_verified"]), (8, 0))
        self.assertEqual([row["ended_with"] for row in result["runs"]], ["model_redraft"] * 8)
        check = live_writer.reverify(result)
        self.assertEqual((check["accepted_still_pass"], check["rejected_still_fail"], check["changed"]), (8, 8, []))

    def test_an_unreachable_model_is_reported_not_hidden(self) -> None:
        result = self._run(unreachable, limit=2)
        summary = result["summary"]
        self.assertEqual((summary["code_written_after_error"], summary["same_end_as_code_written"]), (2, 2))
        self.assertIn("no route to host", result["runs"][0]["errors"][0])
        self.assertEqual(result["runs"][0]["drafts"][-1]["by"], OUTCOME_AFTER_ERROR)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertFalse(live_writer.print_summary(result))
        self.assertIn("ended with a model error", out.getvalue())

    def test_command_line_saves_a_run_and_replays_it_without_a_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, KEY), patch.object(
            ModelRouter, "_http_json_post", staticmethod(repairing)
        ), patch("src.models.router.load_dotenv_file", return_value={}):
            saved = Path(tmp) / "live_writer_test.json"
            with contextlib.redirect_stdout(io.StringIO()) as out:
                code = live_writer.main(["--provider", "openrouter", "--only", "policy_question",
                                         "--save", str(saved)])
            self.assertEqual(code, 0, out.getvalue())
            self.assertEqual(json.loads(saved.read_text(encoding="utf-8"))["summary"]["runs"], 3)
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(live_writer.main(["--replay", str(saved)]), 0)
            self.assertIn("3 of 3 model drafts the runs ended with still pass", out.getvalue())

    def test_command_line_says_what_to_set_when_no_model_is_configured(self) -> None:
        empty = {name: "" for name in ("OPENROUTER_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY", "OLLAMA_ENABLED")}
        with patch.dict(os.environ, empty), patch("src.models.router.load_dotenv_file", return_value={}):
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(live_writer.main(["--provider", "auto"]), 2)
        self.assertIn("No live model is configured", out.getvalue())


if __name__ == "__main__":
    unittest.main()
