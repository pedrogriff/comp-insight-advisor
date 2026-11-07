"""Unit tests for the Checkpoint 5.1 five-node multi-agent coordinator."""

from __future__ import annotations

from datetime import date
from pathlib import Path
import tempfile
import unittest

from src.agents.coordinator import (
    AGENT_TOOL_SCOPES,
    ALL_SPECIALIST_TOOLS,
    DraftClaim,
    DuplicateToolCallError,
    ExecutiveBrief,
    MAX_RETRIEVAL_ATTEMPTS,
    MAX_REVISIONS,
    MultiAgentCoordinator,
    ThreadCheckpointer,
    ToolAccessError,
    _default_writer,
    compare_single_vs_squad,
)
from src.memory.partner_memory import PartnerMemory
from src.retrieval.embeddings import make_embedder
from src.retrieval.policy_search import PLAYBOOK_PATH, PolicyRetriever
from src.tools.interview_search import NoteIndex, load_notes


def _shared_fixtures() -> tuple[PolicyRetriever, NoteIndex]:
    return (
        PolicyRetriever(make_embedder("hashing"), path=PLAYBOOK_PATH),
        NoteIndex(load_notes()),
    )


class MultiAgentCoordinatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy, cls.notes = _shared_fixtures()

    def _make_coordinator(self, **kwargs) -> MultiAgentCoordinator:
        return MultiAgentCoordinator(policy=self.policy, notes=self.notes, **kwargs)

    def test_scoped_tool_isolation_and_duplicate_guard(self) -> None:
        coord = self._make_coordinator()
        self.assertEqual(len(ALL_SPECIALIST_TOOLS), 12)
        for scope in AGENT_TOOL_SCOPES.values():
            self.assertLessEqual(len(scope), 3)

        pro_exec = coord.make_executor("proactive_strategist")
        with self.assertRaises(ToolAccessError):
            pro_exec.call("analyze_reactive_offers_and_counters", vp_org_code="VP_CLOUD_AI")
        with self.assertRaises(ToolAccessError):
            pro_exec.call("ground_cohort_options", vp_org_code="VP_CLOUD_AI", job_family="RESEARCH_SCI")

        rea_exec = coord.make_executor("reactive_analyst")
        with self.assertRaises(ToolAccessError):
            rea_exec.call("analyze_org_cliff_and_equity_health", vp_org_code="VP_CLOUD_AI")
        with self.assertRaises(ToolAccessError):
            rea_exec.call("plan_cohort_front", vp_org_code="VP_CLOUD_AI", job_family="RESEARCH_SCI")

        syn_exec = coord.make_executor("executive_synthesizer")
        with self.assertRaises(ToolAccessError):
            syn_exec.call("analyze_org_cliff_and_equity_health", vp_org_code="VP_CLOUD_AI")

        # Calling the same tool twice with identical arguments in one node turn is blocked.
        pro_exec.call("analyze_org_cliff_and_equity_health", vp_org_code="VP_CLOUD_AI")
        with self.assertRaises(DuplicateToolCallError):
            pro_exec.call("analyze_org_cliff_and_equity_health", vp_org_code="VP_CLOUD_AI")

    def test_parallel_fan_out_and_operator_add_reducer(self) -> None:
        coord = self._make_coordinator()
        state = coord.run(
            "Prepare the Q1 executive retention brief for VP_CLOUD_AI.",
            vp_org_code="VP_CLOUD_AI",
            thread_id="parallel-check",
        )
        self.assertEqual(state.status, "APPROVED")
        self.assertEqual(state.revisions, 0)

        agents_present = {f.agent for f in state.findings}
        self.assertEqual(agents_present, {"proactive_strategist", "reactive_analyst"})

        # Only the two CONVERGENT cohorts retain cohort_front entries for composition.
        front_scopes = sorted(f.scope for f in state.findings if f.kind == "cohort_front")
        self.assertEqual(front_scopes, ["VP_CLOUD_AI AI_ML_ENG", "VP_CLOUD_AI RESEARCH_SCI"])

        # Retrieval attempts per lever stay bounded by MAX_RETRIEVAL_ATTEMPTS.
        for grounded in state.grounded_by_cohort.values():
            for attempts in grounded["retrieval_attempts_by_lever"].values():
                self.assertLessEqual(attempts, MAX_RETRIEVAL_ATTEMPTS)

    def test_org_brief_vs_single_agent_baseline(self) -> None:
        comp = compare_single_vs_squad("VP_CLOUD_AI")
        single = comp["single_agent"]
        squad = comp["multi_agent_squad"]

        self.assertEqual(comp["ledger_budget_usd"], 2_150_000.0)
        self.assertEqual(single["tools_exposed_per_turn"], 12)
        self.assertEqual(single["sequential_tool_rounds"], 15)
        self.assertEqual(single["combined_first_year_cost_usd"], 3_246_000.0)
        self.assertFalse(single["fits_org_budget"])
        self.assertEqual(single["budget_overrun_usd"], 1_096_000.0)

        self.assertEqual(squad["max_tools_per_node"], 3)
        self.assertTrue(squad["parallel_specialist_fan_out"])
        self.assertEqual(squad["status"], "APPROVED")
        self.assertEqual(squad["revisions"], 0)
        self.assertEqual(squad["combined_first_year_cost_usd"], 1_995_600.0)
        self.assertTrue(squad["fits_org_budget"])
        self.assertEqual(squad["budget_headroom_usd"], 154_400.0)
        self.assertEqual(squad["departures_addressed"], 7)
        self.assertEqual(squad["departures_total"], 11)
        self.assertEqual(squad["declined_addressed"], 16)
        self.assertEqual(squad["declined_total"], 16)
        self.assertEqual(squad["joint_evaluations"], 85)
        self.assertEqual(squad["exhaustive_joint_plans"], 1024)

    def test_single_cohort_and_cross_lever_modes(self) -> None:
        coord = self._make_coordinator()
        cohort_state = coord.run(
            "Review retention options for VP_CLOUD_AI RESEARCH_SCI.",
            vp_org_code="VP_CLOUD_AI",
            job_family="RESEARCH_SCI",
            thread_id="single-cohort",
        )
        self.assertEqual(cohort_state.status, "APPROVED")
        assert cohort_state.draft is not None
        self.assertIn("$1,236,800", cohort_state.draft.option_lines[0])
        self.assertEqual(len(cohort_state.draft.uncertainty_disclosures), 2)

        policy_state = coord.run(
            "How do equity caps differ for new-hire offers versus retention grants for current staff?",
            thread_id="cross-lever-ok",
        )
        self.assertEqual(policy_state.status, "APPROVED")
        self.assertEqual(policy_state.findings, [])
        assert policy_state.draft is not None
        self.assertGreaterEqual(len(policy_state.draft.claims), 2)

        # Inject a writer that swaps a new-hire clause onto the current_employees side.
        def swapped_cross_lever_writer(st) -> ExecutiveBrief:
            good = _default_writer(st)
            bad_claims = tuple(
                DraftClaim(
                    side=c.side,
                    clause_id="2.1:thresholds",
                    text="Standard new-hire offers up to 1.00 Compa-Ratio and 1.20x Equity Guideline.",
                )
                for c in good.claims
            )
            return ExecutiveBrief(
                mode=good.mode,
                scope=good.scope,
                headline=good.headline,
                summary=good.summary,
                option_lines=good.option_lines,
                cited_clauses=("2.1:thresholds",),
                sign_offs=good.sign_offs,
                uncertainty_disclosures=good.uncertainty_disclosures,
                memory_notes=good.memory_notes,
                claims=bad_claims,
            )

        bad_coord = self._make_coordinator(writer_fn=swapped_cross_lever_writer)
        bad_state = bad_coord.run(
            "How do equity caps differ for new-hire offers versus retention grants for current staff?",
            max_revisions=1,
            thread_id="cross-lever-bad",
        )
        self.assertEqual(bad_state.status, "HOLD_FOR_HUMAN_REVIEW")
        assert bad_state.review is not None
        self.assertTrue(any("cross_lever_violation" in msg for msg in bad_state.review.issues))

    def test_partner_memory_budget_cap_and_option_ordering(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            mem_db = Path(tmpdir) / "partner_memory.db"
            mem = PartnerMemory(mem_db)
            today = date.today()

            # Confirm a tighter working cap ($1,800,000 < $2,150,000 ledger) and a rank-last preference.
            prop_cap = prop_ord = None
            for idx in range(1, 4):
                prop_cap = mem.record_feedback(
                    "HRBP_CLOUD", "VP_CLOUD_AI", f"s{idx}", "budget_cap_usd", 1_800_000, recorded_on=today
                )
                prop_ord = mem.record_feedback(
                    "HRBP_CLOUD",
                    "VP_CLOUD_AI",
                    f"s{idx}",
                    "rank_last_option",
                    "most coverage at any cost",
                    recorded_on=today,
                )
            assert prop_cap is not None
            assert prop_ord is not None
            mem.confirm(prop_cap.pref_id, "HRBP_CLOUD", confirmed_on=today)
            mem.confirm(prop_ord.pref_id, "HRBP_CLOUD", confirmed_on=today)

            coord = self._make_coordinator(memory=mem)
            state = coord.run(
                "Prepare the Q1 executive retention brief for VP_CLOUD_AI.",
                vp_org_code="VP_CLOUD_AI",
                partner_id="HRBP_CLOUD",
                thread_id="memory-tight-cap",
            )
            self.assertEqual(state.status, "APPROVED")
            assert state.plan is not None
            self.assertEqual(state.plan.ledger_budget_usd, 2_150_000.0)
            self.assertEqual(state.plan.effective_budget_usd, 1_800_000.0)
            assert state.draft is not None
            # Under the $1,800,000 cap, Option 1 inside budget shifts from $1,995,600 to $1,715,000.
            self.assertIn("$1,715,000", state.draft.option_lines[0])
            # "most coverage at any cost" moves to the final slot with an explicit memory note.
            self.assertIn("most coverage at any cost", state.draft.option_lines[-1])
            self.assertEqual(len(state.draft.memory_notes), 1)

            # Confirming a cap above the ledger ($5,000,000) never raises effective_budget_usd above $2,150,000.
            prop_high = None
            for idx in range(4, 7):
                prop_high = mem.record_feedback(
                    "HRBP_CLOUD", "VP_CLOUD_AI", f"s{idx}", "budget_cap_usd", 5_000_000, recorded_on=today
                )
            assert prop_high is not None
            mem.confirm(prop_high.pref_id, "HRBP_CLOUD", confirmed_on=today)
            high_state = coord.run(
                "Prepare the Q1 executive retention brief for VP_CLOUD_AI.",
                vp_org_code="VP_CLOUD_AI",
                partner_id="HRBP_CLOUD",
                thread_id="memory-high-cap",
            )
            assert high_state.plan is not None
            self.assertEqual(high_state.plan.effective_budget_usd, 2_150_000.0)

    def test_bounded_review_loop_recovery_and_escalation(self) -> None:
        # Writer 1: hallucinates $9,999,999 on initial draft, fixes itself on revision #1.
        def flaky_writer(state) -> ExecutiveBrief:
            good = _default_writer(state)
            if state.revisions == 0:
                return ExecutiveBrief(
                    mode=good.mode,
                    scope=good.scope,
                    headline=good.headline,
                    summary=good.summary + " Unverified reserve: $9,999,999.",
                    option_lines=good.option_lines,
                    cited_clauses=(),
                    sign_offs=(),
                    uncertainty_disclosures=(),
                    memory_notes=good.memory_notes,
                )
            return good

        recovering = self._make_coordinator(writer_fn=flaky_writer)
        rec_state = recovering.run(
            "Review retention options for VP_CLOUD_AI RESEARCH_SCI.",
            vp_org_code="VP_CLOUD_AI",
            job_family="RESEARCH_SCI",
            thread_id="recover-v2",
        )
        self.assertEqual(rec_state.status, "APPROVED")
        self.assertEqual(rec_state.revisions, 1)

        # Writer 2: never fixes its hallucinated dollar figure -> stops at MAX_REVISIONS = 2.
        def stubborn_writer(state) -> ExecutiveBrief:
            good = _default_writer(state)
            return ExecutiveBrief(
                mode=good.mode,
                scope=good.scope,
                headline=good.headline,
                summary="Invented spend figure $8,888,888 with 99.9% win rate.",
                option_lines=good.option_lines,
                cited_clauses=(),
                sign_offs=(),
                uncertainty_disclosures=(),
                memory_notes=(),
            )

        capped = self._make_coordinator(writer_fn=stubborn_writer)
        cap_state = capped.run(
            "Review retention options for VP_CLOUD_AI RESEARCH_SCI.",
            vp_org_code="VP_CLOUD_AI",
            job_family="RESEARCH_SCI",
            thread_id="cap-at-two",
        )
        self.assertEqual(cap_state.status, "HOLD_FOR_HUMAN_REVIEW")
        self.assertEqual(cap_state.revisions, MAX_REVISIONS)
        self.assertIn("HOLD_FOR_HUMAN_REVIEW after 2 revision(s)", cap_state.final_output)

    def test_specialist_failover_and_thread_checkpointer(self) -> None:
        checkpointer = ThreadCheckpointer()

        def broken_offers_tool(vp_org_code: str):
            raise RuntimeError(f"offers table offline for {vp_org_code}")

        failing = self._make_coordinator(
            checkpointer=checkpointer,
            tool_overrides={"analyze_reactive_offers_and_counters": broken_offers_tool},
        )
        fail_state = failing.run(
            "Prepare executive brief for VP_CLOUD_AI.",
            vp_org_code="VP_CLOUD_AI",
            thread_id="failover-thread",
        )
        self.assertEqual(fail_state.status, "FAILED_TOOL_ERROR")
        self.assertIsNone(fail_state.draft)
        fail_nodes = [snap.node for snap in checkpointer.history("failover-thread")]
        self.assertEqual(fail_nodes, ["supervisor", "parallel_specialists", "failover"])

        ok_coord = self._make_coordinator(checkpointer=checkpointer)
        ok_coord.run(
            "Review retention options for VP_CLOUD_AI RESEARCH_SCI.",
            vp_org_code="VP_CLOUD_AI",
            job_family="RESEARCH_SCI",
            thread_id="ok-thread",
        )
        ok_history = checkpointer.history("ok-thread")
        self.assertEqual(
            [snap.node for snap in ok_history],
            ["supervisor", "parallel_specialists", "executive_synthesizer", "governance_reviewer", "finalize"],
        )
        # Step 1 snapshot stays immutable even after later nodes append findings and finalize status.
        self.assertEqual(ok_history[0].findings_count, 0)
        self.assertEqual(ok_history[0].status, "IN_PROGRESS")
        self.assertEqual(ok_history[-1].status, "APPROVED")


if __name__ == "__main__":
    unittest.main()
