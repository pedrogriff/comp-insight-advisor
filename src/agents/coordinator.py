"""Multi-agent coordinator, parallel specialist nodes, and bounded review loop.

Implements the Checkpoint 5.1 five-node squad in plain standard-library Python,
matching LangGraph's StateGraph, Send() parallel fan-out, operator.add reducer,
conditional review loop, and per-thread checkpointing:

1. supervisor (fast tier + deterministic routing). Loads PartnerMemory standing
   preferences, classifies the request as an org-wide retention brief, a single
   cohort retention brief, or a cross-lever policy comparison, and emits a
   typed InvestigationPlan.
2. proactive_strategist (fast tier, 3 internal roster and planning tools).
   Computes cashflow cliff exposure, cohort driver fit, and width-3 cohort
   Pareto fronts, appending Finding records via an append-only reducer.
3. reactive_analyst (fast tier, 3 market and interview tools). Runs in parallel
   with proactive_strategist, grading offer acceptance and counter-offer rates
   with 95 percent intervals and retrieving exit notes for convergent cohorts.
4. executive_synthesizer (reasoning tier, 2 policy grounding tools). Composes
   shared-budget Pareto plans across convergent cohorts via plan_org_options(),
   retrieves lever-filtered policy clauses (capped at 2 attempts per lever),
   orders options with PartnerMemory, and drafts a cited ExecutiveBrief.
5. governance_reviewer (structured reviewer + deterministic verifier). Checks
   every dollar figure, percentage, headcount ratio, population rule, sign-off,
   and uncertainty disclosure against the structured tool outputs. Rejects bad
   drafts with targeted feedback for at most MAX_REVISIONS = 2 retries before
   escalating to human review.

From the repo root:
    python3 -m src.agents.coordinator VP_CLOUD_AI
    python3 -m src.agents.coordinator --compare
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import copy
from pathlib import Path
import sys
from typing import Any, Callable

from src.agents.state import (
    AGENT_TOOL_SCOPES,
    ALL_SPECIALIST_TOOLS,
    DraftClaim,
    DuplicateToolCallError,
    ExecutiveBrief,
    Finding,
    InvestigationPlan,
    MAX_RETRIEVAL_ATTEMPTS,
    MAX_REVISIONS,
    ReviewVerdict,
    ScopedToolExecutor,
    SquadState,
    StepSnapshot,
    ThreadCheckpointer,
    ToolAccessError,
    build_tool_map,
    deterministic_verify_brief,
    merge_parallel_updates,
)
from src.memory.partner_memory import PartnerMemory, effective_budget_cap
from src.retrieval.cross_lever import plan_question
from src.retrieval.embeddings import make_embedder
from src.retrieval.policy_search import PLAYBOOK_PATH, PolicyRetriever
from src.tools.deterministic_analytics import DEFAULT_DB_PATH
from src.tools.interview_search import NoteIndex, load_notes

__all__ = [
    "AGENT_TOOL_SCOPES",
    "ALL_SPECIALIST_TOOLS",
    "DraftClaim",
    "DuplicateToolCallError",
    "ExecutiveBrief",
    "Finding",
    "InvestigationPlan",
    "MAX_RETRIEVAL_ATTEMPTS",
    "MAX_REVISIONS",
    "MultiAgentCoordinator",
    "ReviewVerdict",
    "ScopedToolExecutor",
    "SquadState",
    "StepSnapshot",
    "ThreadCheckpointer",
    "ToolAccessError",
    "build_tool_map",
    "compare_single_vs_squad",
    "deterministic_verify_brief",
    "merge_parallel_updates",
    "run_single_agent_baseline",
]


def _default_writer(state: SquadState) -> ExecutiveBrief:
    """Reference deterministic synthesizer used when no external LLM callable is injected."""
    if state.plan and state.plan.mode == "cross_lever_policy":
        res = state.cross_lever_result or {}
        claims: list[DraftClaim] = []
        cited: list[str] = []
        parts: list[str] = []
        for group in res.get("groups", []):
            side = group["side"]
            label = f"{group['population']} ({group['lever'] or 'any lever'})"
            clauses = group.get("clauses", [])
            if clauses:
                top = clauses[0]
                claims.append(DraftClaim(side=side, clause_id=top["id"], text=top["text"]))
                cited.append(top["id"])
                parts.append(f"{label} [{top['id']}]: {top['text']}")
            else:
                parts.append(f"{label}: the compensation governance playbook states no rule for this side.")
        return ExecutiveBrief(
            mode="cross_lever_policy",
            scope="cross_lever",
            headline="Cross-lever policy comparison by population",
            summary=" ".join(parts),
            option_lines=tuple(parts),
            cited_clauses=tuple(dict.fromkeys(cited)),
            sign_offs=(),
            uncertainty_disclosures=(),
            memory_notes=(),
            claims=tuple(claims),
        )

    plan = state.plan
    assert plan is not None
    org_code = plan.vp_org_code or "UNKNOWN_ORG"

    org_health = next((f.payload for f in state.findings if f.kind == "org_cliff_health"), {})
    convergent_families = [
        f.payload["scope"]["job_family"]
        for f in state.findings
        if f.kind == "retention_evidence" and f.payload.get("pattern") == "CONVERGENT"
    ]
    non_convergent = [
        f"{f.payload['scope']['job_family']} ({f.payload['pattern']})"
        for f in state.findings
        if f.kind == "retention_evidence" and f.payload.get("pattern") != "CONVERGENT"
    ]

    cited_clauses: list[str] = []
    for fam in convergent_families:
        g = state.grounded_by_cohort.get(f"{org_code} {fam}", {})
        for hits in g.get("clauses", {}).values():
            for h in hits:
                cited_clauses.append(h["id"])
        for item in g.get("checklist", []):
            if item.get("clause"):
                cited_clauses.append(item["clause"]["id"])
    unique_citations = tuple(dict.fromkeys(cited_clauses))

    raw_prefs = [p for p in state.active_preferences if p.get("key") == "rank_last_option"]
    declined_map = {p["value"]: p for p in raw_prefs}

    sign_offs: list[str] = []
    option_lines: list[str] = []
    memory_notes: list[str] = []

    if state.org_composition:
        comp = state.org_composition
        dep_tot = comp["departures_total"]
        dec_tot = comp["declined_total"]
        opts = list(comp["options"])
        kept, moved = [], []
        for o in opts:
            key_match = declined_map.get(o["signature"]) or declined_map.get(o["role"])
            if key_match:
                note = (
                    f"Option '{o['role']}' moved last per standing preference "
                    f"({key_match['session_count']} prior sessions)."
                )
                memory_notes.append(note)
                moved.append(o)
            else:
                kept.append(o)
        ordered_opts = kept + moved

        cohort_tops = [
            f.payload["options"][0]["first_year_cost_usd"]
            for f in state.findings
            if f.kind == "cohort_front" and f.payload.get("options")
        ]
        standalone_sum = sum(cohort_tops)
        summary = (
            f"{org_code} carries ${plan.effective_budget_usd:,.0f} in effective proactive budget "
            f"(ledger ${plan.ledger_budget_usd:,.0f}). Convergent retention risk holds in "
            f"{', '.join(convergent_families)}; {', '.join(non_convergent) or 'no other cohort'} "
            f"did not meet convergent action gates. Pricing top cohort plans independently totals "
            f"${standalone_sum:,.0f}, exceeding budget by ${standalone_sum - plan.effective_budget_usd:,.0f}, "
            f"so the coordinator composed joint cohort fronts across the shared budget."
        )
        for idx, o in enumerate(ordered_opts, start=1):
            sign_offs.extend(o.get("sign_offs", []))
            per_fam = "; ".join(f"{fam}: {sig}" for fam, sig in o["by_cohort"].items())
            option_lines.append(
                f"Option {idx} ({o['role']}): {o['departures_addressed']} of {dep_tot} departures and "
                f"{o['declined_addressed']} of {dec_tot} declined offers for ${o['first_year_cost_usd']:,.0f} "
                f"[{per_fam}]."
            )
    else:
        front_finding = next((f for f in state.findings if f.kind == "cohort_front"), None)
        if front_finding is None:
            summary = (
                f"No cohort in {org_code} passed the convergent internal-cliff and market-loss gate. "
                f"Budget remains ${plan.effective_budget_usd:,.0f}."
            )
        else:
            p = front_finding.payload
            dep_tot = p["departures_total"]
            dec_tot = p["declined_total"]
            opts = list(p["options"])
            kept, moved = [], []
            for o in opts:
                key_match = declined_map.get(o["signature"]) or declined_map.get(o["role"])
                if key_match:
                    memory_notes.append(
                        f"Plan '{o['signature']}' moved last per standing preference "
                        f"({key_match['session_count']} prior sessions)."
                    )
                    moved.append(o)
                else:
                    kept.append(o)
            ordered_opts = kept + moved
            summary = (
                f"{p['scope']} shows convergent retention and market risk against an effective budget of "
                f"${plan.effective_budget_usd:,.0f} (ledger ${plan.ledger_budget_usd:,.0f})."
            )
            for idx, o in enumerate(ordered_opts, start=1):
                sign_offs.extend(o.get("sign_offs", []))
                option_lines.append(
                    f"Option {idx} ({o['role']}): {o['signature']} addresses "
                    f"{o['departures_addressed']} of {dep_tot} departures and "
                    f"{o['declined_addressed']} of {dec_tot} declined offers for "
                    f"${o['first_year_cost_usd']:,.0f}."
                )

    disclosures: list[str] = []
    convergent_scope_set = {f"{org_code} {fam}" for fam in convergent_families}
    for f in state.findings:
        if f.kind == "retention_evidence" and f.payload.get("pattern") == "CONVERGENT":
            if f.payload.get("uncertainty_disclosure_required"):
                disclosures.append(
                    f"{f.scope} carries {f.payload['evidence_strength']} market evidence; "
                    "95 percent confidence intervals overlap at least one policy threshold."
                )
        if (
            f.kind == "intervention_fit"
            and f.scope in convergent_scope_set
            and f.payload.get("flags", {}).get("thin_driver_evidence")
        ):
            dep_count = f.payload["departures"]["total"]
            disclosures.append(
                f"{f.scope} has fewer than 5 departures ({dep_count} recorded), so driver counts "
                "are reported instead of percentages per playbook Section 5."
            )

    if org_health:
        total_emp = org_health["org_summary"]["total_headcount"]
        cliff_emp = org_health["org_summary"]["cliff_count_gt_15pct"]
        headline = (
            f"{org_code} executive compensation brief: {cliff_emp} cliff cases across {total_emp} employees"
        )
    else:
        headline = f"{org_code} executive compensation brief"

    return ExecutiveBrief(
        mode=plan.mode,
        scope=f"{org_code} {plan.job_family}".strip() if plan.job_family else org_code,
        headline=headline,
        summary=summary,
        option_lines=tuple(option_lines),
        cited_clauses=unique_citations,
        sign_offs=tuple(dict.fromkeys(sign_offs)),
        uncertainty_disclosures=tuple(disclosures),
        memory_notes=tuple(memory_notes),
    )


class MultiAgentCoordinator:
    """Five-node StateGraph-equivalent coordinator for compensation investigations."""

    def __init__(
        self,
        db_path: Path = DEFAULT_DB_PATH,
        policy: PolicyRetriever | None = None,
        notes: NoteIndex | None = None,
        memory: PartnerMemory | None = None,
        writer_fn: Callable[[SquadState], ExecutiveBrief] | None = None,
        critic_fn: Callable[[SquadState, ReviewVerdict], ReviewVerdict] | None = None,
        checkpointer: ThreadCheckpointer | None = None,
        tool_overrides: dict[str, Callable[..., Any]] | None = None,
    ) -> None:
        self.db_path = db_path
        self.policy = policy or PolicyRetriever(make_embedder("hashing"), path=PLAYBOOK_PATH)
        self.notes = notes or NoteIndex(load_notes())
        self.memory = memory
        self.writer_fn = writer_fn or _default_writer
        self.critic_fn = critic_fn
        self.checkpointer = checkpointer or ThreadCheckpointer()
        base_tools = build_tool_map(self.db_path, self.policy, self.notes, self.memory)
        if tool_overrides:
            base_tools.update(tool_overrides)
        self._tools = base_tools

    def make_executor(self, agent_name: str) -> ScopedToolExecutor:
        return ScopedToolExecutor(agent_name, self._tools, AGENT_TOOL_SCOPES[agent_name])

    def supervisor_node(self, state: SquadState) -> SquadState:
        executor = self.make_executor("supervisor")
        q_plan = plan_question(state.question)
        is_policy_only = (
            state.vp_org_code is None
            and len(q_plan.get("sides", [])) >= 2
            and any(w in state.question.lower() for w in ("compare", "versus", "vs", "differ", "policy", "cap"))
        )
        if is_policy_only:
            state.plan = InvestigationPlan(
                mode="cross_lever_policy",
                vp_org_code=None,
                job_family=None,
                cohorts=(),
                specialists=(),
                proactive_task="",
                reactive_task="",
                synthesis_task=f"Run side-by-side filtered retrieval for: {state.question}",
                ledger_budget_usd=0.0,
                effective_budget_usd=0.0,
            )
            state.messages.append("supervisor -> executive_synthesizer: cross-lever policy comparison")
            state.tool_calls.extend(executor.call_log)
            return state

        org_code = state.vp_org_code or "VP_CLOUD_AI"
        state.vp_org_code = org_code
        org_info = executor.call("list_org_cohorts", vp_org_code=org_code)
        mem_info = executor.call("load_partner_memory", partner_id=state.partner_id, vp_org_code=org_code)
        state.active_preferences = mem_info["apply"]
        state.pending_preferences = mem_info["ask_partner"]
        ledger_usd = float(org_info["ledger_budget_usd"])
        eff_usd = effective_budget_cap(mem_info.get("_raw_apply", []), ledger_usd)

        if state.job_family:
            cohorts = ((org_code, state.job_family),)
            mode = "cohort_retention_brief"
        else:
            cohorts = tuple((org_code, fam) for fam in org_info["job_families"])
            mode = "org_retention_brief"

        state.plan = InvestigationPlan(
            mode=mode,
            vp_org_code=org_code,
            job_family=state.job_family,
            cohorts=cohorts,
            specialists=("proactive_strategist", "reactive_analyst"),
            proactive_task=f"Scan cashflow cliffs, driver fit, and width-3 cohort fronts for {org_code}.",
            reactive_task=f"Grade offer/counter win rates with 95% intervals and pull exit notes for {org_code}.",
            synthesis_task=f"Compose in-budget Pareto options under ${eff_usd:,.0f} and ground policy clauses.",
            ledger_budget_usd=ledger_usd,
            effective_budget_usd=eff_usd,
        )
        state.messages.append(
            f"supervisor -> [proactive_strategist, reactive_analyst]: parallel dispatch for {len(cohorts)} cohort(s)"
        )
        state.tool_calls.extend(executor.call_log)
        return state

    def fan_out_from_supervisor(self, state: SquadState) -> list[str]:
        if state.plan and state.plan.specialists:
            return list(state.plan.specialists)
        return ["executive_synthesizer"]

    def proactive_strategist_node(self, state: SquadState) -> dict[str, Any]:
        executor = self.make_executor("proactive_strategist")
        findings: list[Finding] = []
        errors: list[str] = []
        messages: list[str] = []
        assert state.plan is not None
        org_code = state.plan.vp_org_code or "VP_CLOUD_AI"
        try:
            org_health = executor.call("analyze_org_cliff_and_equity_health", vp_org_code=org_code)
            findings.append(
                Finding(
                    agent="proactive_strategist",
                    kind="org_cliff_health",
                    scope=org_code,
                    summary=(
                        f"{org_health['org_summary']['cliff_count_gt_15pct']} severe cliffs across "
                        f"{org_health['org_summary']['total_headcount']} employees"
                    ),
                    payload=org_health,
                )
            )
            for org, fam in state.plan.cohorts:
                fit = executor.call("assess_intervention_fit", vp_org_code=org, job_family=fam)
                findings.append(
                    Finding(
                        agent="proactive_strategist",
                        kind="intervention_fit",
                        scope=f"{org} {fam}",
                        summary=f"{fit['departures']['total']} departures, mismatch={fit['flags']['default_lever_mismatch']}",
                        payload=fit,
                    )
                )
                if fit["departures"]["total"] > 0 or fit["declined_offers"]["total"] > 0:
                    front = executor.call(
                        "plan_cohort_front",
                        vp_org_code=org,
                        job_family=fam,
                        budget_cap_usd=state.plan.effective_budget_usd,
                    )
                    findings.append(
                        Finding(
                            agent="proactive_strategist",
                            kind="cohort_front",
                            scope=f"{org} {fam}",
                            summary=(
                                f"{front['evaluations']} plans evaluated, {front['front_count']} composable Pareto plans"
                            ),
                            payload=front,
                        )
                    )
            messages.append(f"proactive_strategist -> executive_synthesizer: appended {len(findings)} findings")
        except Exception as exc:
            errors.append(f"proactive_strategist error: {exc}")
            messages.append(f"proactive_strategist -> failover: {exc}")
        return {
            "findings": findings,
            "errors": errors,
            "messages": messages,
            "tool_calls": executor.call_log,
        }

    def reactive_analyst_node(self, state: SquadState) -> dict[str, Any]:
        executor = self.make_executor("reactive_analyst")
        findings: list[Finding] = []
        errors: list[str] = []
        messages: list[str] = []
        assert state.plan is not None
        org_code = state.plan.vp_org_code or "VP_CLOUD_AI"
        try:
            reactive = executor.call("analyze_reactive_offers_and_counters", vp_org_code=org_code)
            findings.append(
                Finding(
                    agent="reactive_analyst",
                    kind="reactive_offers",
                    scope=org_code,
                    summary=f"{len(reactive['policy_escalation_triggers'])} escalation trigger(s)",
                    payload=reactive,
                )
            )
            for org, fam in state.plan.cohorts:
                ev = executor.call("assess_retention_evidence", vp_org_code=org, job_family=fam)
                findings.append(
                    Finding(
                        agent="reactive_analyst",
                        kind="retention_evidence",
                        scope=f"{org} {fam}",
                        summary=f"pattern={ev['pattern']}, strength={ev['evidence_strength']}",
                        payload=ev,
                    )
                )
                if ev["pattern"] == "CONVERGENT":
                    exit_notes = executor.call("search_exit_notes", vp_org_code=org, job_family=fam, query="")
                    findings.append(
                        Finding(
                            agent="reactive_analyst",
                            kind="exit_notes",
                            scope=f"{org} {fam}",
                            summary=f"{len(exit_notes)} exit note(s) retrieved",
                            payload={"scope": f"{org} {fam}", "notes": exit_notes},
                        )
                    )
            messages.append(f"reactive_analyst -> executive_synthesizer: appended {len(findings)} findings")
        except Exception as exc:
            errors.append(f"reactive_analyst error: {exc}")
            messages.append(f"reactive_analyst -> failover: {exc}")
        return {
            "findings": findings,
            "errors": errors,
            "messages": messages,
            "tool_calls": executor.call_log,
        }

    def route_after_specialists(self, state: SquadState) -> str:
        return "failover" if state.errors else "executive_synthesizer"

    def executive_synthesizer_node(self, state: SquadState) -> SquadState:
        assert state.plan is not None
        if state.revisions == 0:
            executor = self.make_executor("executive_synthesizer")
            if state.plan.mode == "cross_lever_policy":
                state.cross_lever_result = executor.call(
                    "compare_cross_lever_policies", question=state.question
                )
            else:
                convergent = [
                    (f.payload["scope"]["vp_org_code"], f.payload["scope"]["job_family"])
                    for f in state.findings
                    if f.kind == "retention_evidence" and f.payload.get("pattern") == "CONVERGENT"
                ]
                convergent_scopes = {f"{o} {fam}" for o, fam in convergent}
                state.findings = [
                    f for f in state.findings if f.kind != "cohort_front" or f.scope in convergent_scopes
                ]
                if len(convergent) >= 2:
                    sup_exec = self.make_executor("supervisor")
                    state.org_composition = sup_exec.call(
                        "compose_org_options",
                        cohorts=convergent,
                        budget_usd=state.plan.effective_budget_usd,
                    )
                    state.tool_calls.extend(sup_exec.call_log)
                    state.messages.append(
                        f"supervisor: composed shared-budget Pareto front across {len(convergent)} convergent cohorts"
                    )
                for org, fam in convergent:
                    state.grounded_by_cohort[f"{org} {fam}"] = executor.call(
                        "ground_cohort_options", vp_org_code=org, job_family=fam
                    )
            state.tool_calls.extend(executor.call_log)

        state.draft = self.writer_fn(state)
        pass_label = "initial draft" if state.revisions == 0 else f"revision #{state.revisions}"
        state.messages.append(f"executive_synthesizer -> governance_reviewer: {pass_label} ready")
        return state

    def governance_reviewer_node(self, state: SquadState) -> SquadState:
        executor = self.make_executor("governance_reviewer")
        verdict = executor.call("verify_brief", state=state)
        if self.critic_fn is not None:
            verdict = self.critic_fn(state, verdict)
        state.review = verdict
        state.tool_calls.extend(executor.call_log)
        if verdict.approved:
            state.messages.append("governance_reviewer -> finalize: approved")
        else:
            state.messages.append(
                f"governance_reviewer -> executive_synthesizer: rejected ({len(verdict.issues)} issue(s))"
            )
        return state

    def route_after_review(self, state: SquadState) -> str:
        assert state.review is not None
        if state.review.approved:
            return "finalize"
        if state.revisions < state.max_revisions:
            return "revise"
        return "escalate_unverified"

    def finalize_node(self, state: SquadState) -> SquadState:
        assert state.draft is not None
        state.status = "APPROVED"
        lines = [
            f"# {state.draft.headline}",
            state.draft.summary,
            *state.draft.option_lines,
        ]
        if state.draft.sign_offs:
            lines.append("Required sign-offs: " + "; ".join(state.draft.sign_offs))
        if state.draft.cited_clauses:
            lines.append("Cited clauses: " + ", ".join(state.draft.cited_clauses))
        for disc in state.draft.uncertainty_disclosures:
            lines.append("Disclosure: " + disc)
        for note in state.draft.memory_notes:
            lines.append("Partner memory: " + note)
        state.final_output = "\n".join(lines)
        state.messages.append("finalize: published verified executive brief")
        return state

    def failover_node(self, state: SquadState) -> SquadState:
        state.status = "FAILED_TOOL_ERROR"
        state.final_output = "FAILED_TOOL_ERROR: " + "; ".join(state.errors)
        state.messages.append("failover: halted workflow on specialist tool error")
        return state

    def escalate_unverified_node(self, state: SquadState) -> SquadState:
        state.status = "HOLD_FOR_HUMAN_REVIEW"
        issues = "; ".join(state.review.issues) if state.review else "unknown verification failure"
        state.final_output = f"HOLD_FOR_HUMAN_REVIEW after {state.revisions} revision(s): {issues}"
        state.messages.append("escalate_unverified: capped review loop and held brief for human review")
        return state

    def run(
        self,
        question: str,
        vp_org_code: str | None = None,
        job_family: str | None = None,
        partner_id: str = "HRBP_DEFAULT",
        max_revisions: int = MAX_REVISIONS,
        thread_id: str = "default-thread",
    ) -> SquadState:
        state = SquadState(
            question=question,
            vp_org_code=vp_org_code,
            job_family=job_family,
            partner_id=partner_id,
            max_revisions=max_revisions,
        )
        state = self.supervisor_node(state)
        self.checkpointer.save(thread_id, "supervisor", state)

        targets = self.fan_out_from_supervisor(state)
        if targets == ["proactive_strategist", "reactive_analyst"]:
            left_copy = copy.deepcopy(state)
            right_copy = copy.deepcopy(state)
            with ThreadPoolExecutor(max_workers=2) as pool:
                fut_pro = pool.submit(self.proactive_strategist_node, left_copy)
                fut_rea = pool.submit(self.reactive_analyst_node, right_copy)
                updates = [fut_pro.result(), fut_rea.result()]
            state = merge_parallel_updates(state, updates)
            self.checkpointer.save(thread_id, "parallel_specialists", state)
            if self.route_after_specialists(state) == "failover":
                state = self.failover_node(state)
                self.checkpointer.save(thread_id, "failover", state)
                return state

        while True:
            state = self.executive_synthesizer_node(state)
            self.checkpointer.save(thread_id, "executive_synthesizer", state)

            state = self.governance_reviewer_node(state)
            self.checkpointer.save(thread_id, "governance_reviewer", state)

            nxt = self.route_after_review(state)
            if nxt == "finalize":
                state = self.finalize_node(state)
                self.checkpointer.save(thread_id, "finalize", state)
                return state
            if nxt == "revise":
                state.revisions += 1
                continue
            state = self.escalate_unverified_node(state)
            self.checkpointer.save(thread_id, "escalate_unverified", state)
            return state


def run_single_agent_baseline(
    question: str,
    vp_org_code: str = "VP_CLOUD_AI",
    db_path: Path = DEFAULT_DB_PATH,
    policy: PolicyRetriever | None = None,
    notes: NoteIndex | None = None,
) -> dict[str, Any]:
    """Baseline: one generalist agent holding all tools sequentially without org composition."""
    pol = policy or PolicyRetriever(make_embedder("hashing"), path=PLAYBOOK_PATH)
    note_idx = notes or NoteIndex(load_notes())
    tools = build_tool_map(db_path, pol, note_idx, memory=None)
    executor = ScopedToolExecutor("single_generalist", tools, ALL_SPECIALIST_TOOLS)

    org_info = executor.call("list_org_cohorts", vp_org_code=vp_org_code)
    budget_usd = float(org_info["ledger_budget_usd"])
    executor.call("analyze_org_cliff_and_equity_health", vp_org_code=vp_org_code)
    executor.call("analyze_reactive_offers_and_counters", vp_org_code=vp_org_code)

    standalone_picks: list[dict[str, Any]] = []
    sequential_rounds = 3
    for fam in org_info["job_families"]:
        ev = executor.call("assess_retention_evidence", vp_org_code=vp_org_code, job_family=fam)
        sequential_rounds += 1
        if ev["pattern"] == "CONVERGENT":
            executor.call("assess_intervention_fit", vp_org_code=vp_org_code, job_family=fam)
            front = executor.call("plan_cohort_front", vp_org_code=vp_org_code, job_family=fam)
            executor.call("search_exit_notes", vp_org_code=vp_org_code, job_family=fam, query="")
            executor.call("ground_cohort_options", vp_org_code=vp_org_code, job_family=fam)
            sequential_rounds += 4
            top = front["options"][0]
            standalone_picks.append(
                {
                    "job_family": fam,
                    "signature": top["signature"],
                    "departures_addressed": top["departures_addressed"],
                    "declined_addressed": top["declined_addressed"],
                    "first_year_cost_usd": top["first_year_cost_usd"],
                }
            )

    combined_cost = sum(p["first_year_cost_usd"] for p in standalone_picks)
    return {
        "architecture": "single_generalist_agent",
        "vp_org_code": vp_org_code,
        "tools_exposed_per_turn": len(ALL_SPECIALIST_TOOLS),
        "sequential_tool_rounds": sequential_rounds,
        "total_tool_calls": len(executor.call_log),
        "ledger_budget_usd": budget_usd,
        "combined_first_year_cost_usd": combined_cost,
        "fits_org_budget": combined_cost <= budget_usd,
        "budget_overrun_usd": max(0.0, combined_cost - budget_usd),
        "departures_addressed": sum(p["departures_addressed"] for p in standalone_picks),
        "declined_addressed": sum(p["declined_addressed"] for p in standalone_picks),
        "standalone_picks": standalone_picks,
    }


def compare_single_vs_squad(
    vp_org_code: str = "VP_CLOUD_AI",
    db_path: Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    """Side-by-side benchmark of 1 generalist agent vs. the 5-node squad on an org brief."""
    pol = PolicyRetriever(make_embedder("hashing"), path=PLAYBOOK_PATH)
    note_idx = NoteIndex(load_notes())
    question = f"Prepare the Q1 executive retention and offer brief for {vp_org_code}."

    single = run_single_agent_baseline(question, vp_org_code=vp_org_code, db_path=db_path, policy=pol, notes=note_idx)
    coord = MultiAgentCoordinator(db_path=db_path, policy=pol, notes=note_idx)
    squad_state = coord.run(question, vp_org_code=vp_org_code, thread_id="compare-squad")

    assert squad_state.org_composition is not None
    opt1 = squad_state.org_composition["options"][0]
    max_specialist_tools = max(len(tools) for tools in AGENT_TOOL_SCOPES.values())

    return {
        "vp_org_code": vp_org_code,
        "ledger_budget_usd": single["ledger_budget_usd"],
        "single_agent": single,
        "multi_agent_squad": {
            "architecture": "five_node_state_graph",
            "max_tools_per_node": max_specialist_tools,
            "parallel_specialist_fan_out": True,
            "total_tool_calls": len(squad_state.tool_calls),
            "messages_exchanged": len(squad_state.messages),
            "revisions": squad_state.revisions,
            "status": squad_state.status,
            "combined_first_year_cost_usd": opt1["first_year_cost_usd"],
            "fits_org_budget": opt1["fits_remaining_budget"],
            "budget_headroom_usd": single["ledger_budget_usd"] - opt1["first_year_cost_usd"],
            "departures_addressed": opt1["departures_addressed"],
            "departures_total": squad_state.org_composition["departures_total"],
            "declined_addressed": opt1["declined_addressed"],
            "declined_total": squad_state.org_composition["declined_total"],
            "joint_evaluations": squad_state.org_composition["evaluations"],
            "exhaustive_joint_plans": 32 ** len(squad_state.org_composition["cohorts"]),
            "by_cohort": opt1["by_cohort"],
        },
    }


def _print_comparison(comp: dict[str, Any]) -> None:
    s = comp["single_agent"]
    m = comp["multi_agent_squad"]
    print(f"Org benchmark: {comp['vp_org_code']} (shared proactive budget ${comp['ledger_budget_usd']:,.0f})")
    print(
        f"  1 generalist agent : {s['tools_exposed_per_turn']} tools in one prompt, "
        f"sequential rounds={s['sequential_tool_rounds']}, "
        f"combined cost=${s['combined_first_year_cost_usd']:,.0f} "
        f"(fits_budget={s['fits_org_budget']}, overrun=${s['budget_overrun_usd']:,.0f})"
    )
    print(
        f"  5-node squad       : max {m['max_tools_per_node']} tools/node, parallel fan-out, "
        f"combined cost=${m['combined_first_year_cost_usd']:,.0f} "
        f"(fits_budget={m['fits_org_budget']}, headroom=${m['budget_headroom_usd']:,.0f}), "
        f"coverage={m['departures_addressed']}/{m['departures_total']} departures and "
        f"{m['declined_addressed']}/{m['declined_total']} declined offers in "
        f"{m['joint_evaluations']} evaluations vs {m['exhaustive_joint_plans']} exhaustive"
    )


if __name__ == "__main__":
    cli_args = sys.argv[1:]
    if "--compare" in cli_args:
        _print_comparison(compare_single_vs_squad())
    else:
        org = cli_args[0] if cli_args else "VP_CLOUD_AI"
        fam = cli_args[1] if len(cli_args) >= 2 else None
        coordinator = MultiAgentCoordinator()
        out_state = coordinator.run(
            f"Prepare an executive retention brief for {org}{(' ' + fam) if fam else ''}.",
            vp_org_code=org,
            job_family=fam,
        )
        print(out_state.final_output)
        print(
            f"\n[telemetry] status={out_state.status} findings={len(out_state.findings)} "
            f"tool_calls={len(out_state.tool_calls)} messages={len(out_state.messages)} "
            f"revisions={out_state.revisions}"
        )
