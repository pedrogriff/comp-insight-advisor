"""Tests for the LangGraph engine of the squad.

The first class needs no LangGraph. It walks the graph's node wrappers in
the order the edges declare and requires the same result as the
standard-library engine. The second class runs the compiled StateGraph and
skips where LangGraph is not installed.
"""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from src.agents.coordinator import MAX_REVISIONS, ExecutiveBrief, MultiAgentCoordinator, _default_writer
from src.agents.graph import (
    LangGraphSquad,
    SquadNodes,
    drive_without_langgraph,
    langgraph_available,
    sqlite_saver_available,
)
from src.retrieval.embeddings import make_embedder
from src.retrieval.policy_search import PLAYBOOK_PATH, PolicyRetriever
from src.tools.interview_search import NoteIndex, load_notes

ORG_QUESTION = "Prepare the Q1 executive retention brief for VP_CLOUD_AI."
POLICY_QUESTION = "How do equity caps differ for new-hire offers versus retention grants for current staff?"
SQUAD_NODES = ["supervisor", "parallel_specialists", "executive_synthesizer", "governance_reviewer", "finalize"]


def _flaky_writer(state) -> ExecutiveBrief:
    good = _default_writer(state)
    if state.revisions == 0:
        return ExecutiveBrief(
            mode=good.mode, scope=good.scope, headline=good.headline,
            summary=good.summary + " Unverified reserve: $9,999,999.", option_lines=good.option_lines,
            cited_clauses=(), sign_offs=(), uncertainty_disclosures=(), memory_notes=good.memory_notes,
        )
    return good


def _stubborn_writer(state) -> ExecutiveBrief:
    good = _default_writer(state)
    return ExecutiveBrief(
        mode=good.mode, scope=good.scope, headline=good.headline,
        summary="Invented spend figure $8,888,888 with 99.9% win rate.", option_lines=good.option_lines,
        cited_clauses=(), sign_offs=(), uncertainty_disclosures=(), memory_notes=(),
    )


def _broken_offers_tool(vp_org_code: str):
    raise RuntimeError(f"offers table offline for {vp_org_code}")


class _Fixtures(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = PolicyRetriever(make_embedder("hashing"), path=PLAYBOOK_PATH)
        cls.notes = NoteIndex(load_notes())

    def _coordinator(self, **kwargs) -> MultiAgentCoordinator:
        return MultiAgentCoordinator(policy=self.policy, notes=self.notes, **kwargs)


class GraphNodeWrapperTests(_Fixtures):
    """Runs everywhere: the node wrappers, the JSON state and the route flags."""

    def test_wrappers_match_the_standard_library_engine_in_every_mode(self) -> None:
        cases = [
            (ORG_QUESTION, dict(vp_org_code="VP_CLOUD_AI"), SQUAD_NODES),
            ("Prepare the brief.", dict(vp_org_code="VP_ENT_APPS"), SQUAD_NODES),
            ("Review options.", dict(vp_org_code="VP_SEC_INTEL", job_family="CYBER_SEC_ENG"), SQUAD_NODES),
            (POLICY_QUESTION, dict(), ["supervisor", "executive_synthesizer", "governance_reviewer", "finalize"]),
        ]
        for question, scope, nodes in cases:
            coord = self._coordinator()
            expected = coord.run(question, thread_id="std", **scope)
            got, trace = drive_without_langgraph(SquadNodes(coord), coord.initial_state(question, **scope))
            self.assertEqual(got, expected, scope)
            self.assertEqual(trace, nodes)

        coord = self._coordinator()
        org_state, _ = drive_without_langgraph(SquadNodes(coord), coord.initial_state(ORG_QUESTION, "VP_CLOUD_AI"))
        self.assertEqual(org_state.status, "APPROVED")
        self.assertIn("7 of 11 departures and 16 of 16 declined offers for $1,995,600", org_state.final_output)

    def test_review_loop_escalation_and_failover_routes(self) -> None:
        recovering = self._coordinator(writer_fn=_flaky_writer)
        state, trace = drive_without_langgraph(
            SquadNodes(recovering), recovering.initial_state("Review.", "VP_CLOUD_AI", "RESEARCH_SCI")
        )
        self.assertEqual((state.status, state.revisions), ("APPROVED", 1))
        self.assertEqual(trace.count("executive_synthesizer"), 2)

        capped = self._coordinator(writer_fn=_stubborn_writer)
        state, trace = drive_without_langgraph(
            SquadNodes(capped), capped.initial_state("Review.", "VP_CLOUD_AI", "RESEARCH_SCI")
        )
        self.assertEqual((state.status, state.revisions), ("HOLD_FOR_HUMAN_REVIEW", MAX_REVISIONS))
        self.assertEqual(trace[-1], "escalate_unverified")
        self.assertEqual(trace.count("governance_reviewer"), MAX_REVISIONS + 1)

        failing = self._coordinator(tool_overrides={"analyze_reactive_offers_and_counters": _broken_offers_tool})
        state, trace = drive_without_langgraph(SquadNodes(failing), failing.initial_state(ORG_QUESTION, "VP_CLOUD_AI"))
        self.assertEqual(state.status, "FAILED_TOOL_ERROR")
        self.assertEqual(trace, ["supervisor", "parallel_specialists", "failover"])

    def test_gate_payload_at_the_gate_node(self) -> None:
        from src.guardrails.approval import gate_payload

        def state_at_gate(org: str):
            coord = self._coordinator()
            nodes = SquadNodes(coord)
            state = {"squad": nodes.dump(coord.initial_state("Prepare the brief.", org)), "findings": [],
                     "messages": [], "tool_calls": [], "errors": []}
            state.update(nodes.supervisor(state))
            for update in (nodes.proactive_strategist(state), nodes.reactive_analyst(state)):
                for key in ("findings", "messages", "tool_calls", "errors"):
                    state[key] = state[key] + update[key]
            state.update(nodes.join_specialists(state))
            state.update(nodes.executive_synthesizer(state))
            state.update(nodes.governance_reviewer(state))
            self.assertEqual(state["route"], "finalize")
            return nodes.load(state)

        waiting = state_at_gate("VP_CLOUD_AI")
        self.assertEqual(waiting.status, "IN_PROGRESS")
        payload = gate_payload(waiting)
        self.assertEqual(payload["route"], "EXECUTIVE_SIGN_OFF")
        self.assertEqual(payload["options"][0]["approvers"], ["VP", "Head of Compensation"])
        self.assertEqual(payload["options"][1]["approvers"], ["VP", "Head of Compensation", "Calibration committee"])
        self.assertIsNone(gate_payload(state_at_gate("VP_ENT_APPS")))

    def test_missing_langgraph_is_reported_not_crashed(self) -> None:
        self.assertIsInstance(langgraph_available(), bool)
        self.assertIsInstance(sqlite_saver_available(), bool)
        if not langgraph_available():
            with self.assertRaises(RuntimeError):
                LangGraphSquad(coordinator=self._coordinator())


@unittest.skipUnless(langgraph_available(), "langgraph is not installed")
class LangGraphEngineTests(_Fixtures):
    """Runs where LangGraph is installed: the compiled StateGraph against the other engine."""

    def test_org_brief_matches_the_standard_library_engine(self) -> None:
        expected = self._coordinator().run(ORG_QUESTION, vp_org_code="VP_CLOUD_AI", thread_id="std")
        squad = LangGraphSquad(coordinator=self._coordinator())
        got, pending = squad.run(ORG_QUESTION, vp_org_code="VP_CLOUD_AI", thread_id="lg-org")
        self.assertIsNone(pending)
        self.assertEqual(got.status, "APPROVED")
        self.assertIn("7 of 11 departures and 16 of 16 declined offers for $1,995,600", got.final_output)
        self.assertEqual(got.final_output, expected.final_output)
        self.assertEqual(got, expected)
        self.assertEqual(squad.node_trace("lg-org"), SQUAD_NODES)

    def test_other_modes_match(self) -> None:
        cases = [
            ("Prepare the brief.", dict(vp_org_code="VP_ENT_APPS")),
            ("Review options.", dict(vp_org_code="VP_SEC_INTEL", job_family="CYBER_SEC_ENG")),
            (POLICY_QUESTION, dict()),
        ]
        for i, (question, scope) in enumerate(cases):
            expected = self._coordinator().run(question, thread_id="std", **scope)
            got, pending = LangGraphSquad(coordinator=self._coordinator()).run(question, thread_id=f"lg-{i}", **scope)
            self.assertIsNone(pending)
            self.assertEqual(got, expected, scope)

    def test_review_loop_escalation_and_failover(self) -> None:
        got, _ = LangGraphSquad(coordinator=self._coordinator(writer_fn=_flaky_writer)).run(
            "Review.", vp_org_code="VP_CLOUD_AI", job_family="RESEARCH_SCI", thread_id="lg-flaky"
        )
        self.assertEqual((got.status, got.revisions), ("APPROVED", 1))
        got, _ = LangGraphSquad(coordinator=self._coordinator(writer_fn=_stubborn_writer)).run(
            "Review.", vp_org_code="VP_CLOUD_AI", job_family="RESEARCH_SCI", thread_id="lg-stubborn"
        )
        self.assertEqual((got.status, got.revisions), ("HOLD_FOR_HUMAN_REVIEW", MAX_REVISIONS))
        failing = self._coordinator(tool_overrides={"analyze_reactive_offers_and_counters": _broken_offers_tool})
        got, _ = LangGraphSquad(coordinator=failing).run(ORG_QUESTION, vp_org_code="VP_CLOUD_AI", thread_id="lg-fail")
        self.assertEqual(got.status, "FAILED_TOOL_ERROR")

    def test_interrupt_pauses_at_the_gate_and_resumes(self) -> None:
        from src.guardrails.approval import gate_payload

        squad = LangGraphSquad(coordinator=self._coordinator(), gate=gate_payload)
        paused, pending = squad.run(ORG_QUESTION, vp_org_code="VP_CLOUD_AI", thread_id="lg-gate")
        self.assertIsNotNone(pending)
        self.assertEqual(pending["route"], "EXECUTIVE_SIGN_OFF")
        self.assertEqual([o["index"] for o in pending["options"]], [1, 2, 3])
        self.assertEqual(paused.final_output, "")  # nothing is published while a person decides
        self.assertIsNone(paused.approval)

        decision = {"decision": "approve", "reviewer": "HRBP_CLOUD", "option_index": 1}
        done = squad.resume("lg-gate", decision)
        self.assertEqual(done.status, "APPROVED")
        self.assertEqual(done.approval, decision)
        self.assertIn("$1,995,600", done.final_output)

        # A no-spend brief needs nobody, so the same graph runs straight through.
        free, nothing = squad.run("Prepare the brief.", vp_org_code="VP_ENT_APPS", thread_id="lg-auto")
        self.assertIsNone(nothing)
        self.assertEqual(free.status, "APPROVED")

    @unittest.skipUnless(sqlite_saver_available(), "langgraph-checkpoint-sqlite is not installed")
    def test_paused_run_survives_a_restart_in_sqlite(self) -> None:
        from src.guardrails.approval import gate_payload

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "langgraph.sqlite"
            first = LangGraphSquad(coordinator=self._coordinator(), gate=gate_payload, sqlite_path=db_path)
            _, pending = first.run(ORG_QUESTION, vp_org_code="VP_CLOUD_AI", thread_id="lg-durable")
            self.assertIsNotNone(pending)

            second = LangGraphSquad(coordinator=self._coordinator(), gate=gate_payload, sqlite_path=db_path)
            still_paused, payload = second.snapshot("lg-durable")
            self.assertEqual(payload["route"], "EXECUTIVE_SIGN_OFF")
            self.assertEqual(still_paused.final_output, "")
            done = second.resume("lg-durable", {"decision": "approve", "reviewer": "HRBP_CLOUD", "option_index": 3})
            self.assertEqual(done.status, "APPROVED")
            self.assertEqual(done.approval["option_index"], 3)

    def test_guarded_advisor_runs_on_langgraph_engine(self) -> None:
        from src.guardrails.pipeline import AWAITING_APPROVAL, GuardedAdvisor

        with tempfile.TemporaryDirectory() as tmp:
            advisor = GuardedAdvisor(runtime_dir=tmp, engine="langgraph")
            self.assertEqual(advisor.engine, "langgraph")
            res = advisor.run(ORG_QUESTION, vp_org_code="VP_CLOUD_AI")
            self.assertEqual(res.status, AWAITING_APPROVAL)
            self.assertIn("$1,995,600", res.brief)
            self.assertEqual([n["node"] for n in advisor.trace(res.thread_id)["nodes"]], SQUAD_NODES)


if __name__ == "__main__":
    unittest.main()
