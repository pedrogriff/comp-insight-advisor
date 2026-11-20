"""GuardedAdvisor: the squad behind its guardrails, monitor and approval gate.

One request moves through these steps, and each writes a line to the audit log:

1. Integrity. The playbook must match its recorded hash, or the run is held.
2. Request screen. Out-of-scope, unsafe or unanswerable requests stop here.
3. The squad. Five agents with scoped tools on read-only data, limited to the
   partner's VP orgs, with the figure verifier in a review loop of 2 rounds.
4. Output check and runtime monitor on the finished run.
5. Risk routing. A no-spend brief or a cited policy answer is released. A
   brief with costed options waits for the partner. An option that needs a
   named approver waits for that sign-off to be acknowledged. A run that
   failed any check is held.
6. Release. The verified text gets a governance checklist, the decision
   record, a label saying an AI assistant drafted it, and its provenance.

The advisor never grants, changes or sends anything. A release is a document.

From the repo root:
    python3 -m src.guardrails.pipeline run VP_CLOUD_AI
    python3 -m src.guardrails.pipeline run VP_ENT_APPS
    python3 -m src.guardrails.pipeline ask "How do equity caps differ for new hires versus current staff?"
    python3 -m src.guardrails.pipeline pending
    python3 -m src.guardrails.pipeline triggers
    python3 -m src.guardrails.pipeline approve THREAD --option 1 --ack "VP" --ack "Head of Compensation"
    python3 -m src.guardrails.pipeline reject THREAD --reason data_looks_wrong
    python3 -m src.guardrails.pipeline trace THREAD
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import hashlib
from pathlib import Path
import sys
import time
from typing import Any, Callable
import uuid

from src.agents.checkpoint_store import SqliteThreadCheckpointer
from src.agents.coordinator import MultiAgentCoordinator, is_policy_comparison
from src.agents.graph import LangGraphSquad, langgraph_available, sqlite_saver_available
from src.agents.state import ExecutiveBrief, OrgAccessError, SquadState
from src.guardrails import integrity
from src.guardrails.approval import (
    ROUTE_AUTO,
    ROUTE_HOLD,
    ApprovalError,
    ApprovalStore,
    OptionGate,
    RiskAssessment,
    assess_risk,
)
from src.guardrails.audit import AuditLog, verify_chain
from src.guardrails.input_guard import ALLOW, REFUSE, PartnerContext, load_known_people, load_scope, screen_request
from src.guardrails.monitor import review_trajectory
from src.guardrails.output_guard import check_brief
from src.memory.partner_memory import PartnerMemory
from src.tools.deterministic_analytics import DEFAULT_DB_PATH

PROJECT_ROOT = integrity.PROJECT_ROOT
DEFAULT_RUNTIME_DIR = PROJECT_ROOT / "runtime"
AI_LABEL = (
    "Drafted by an AI assistant from tool outputs and playbook clauses. A compensation partner reviews it, "
    "and a person decides."
)

RELEASED = "RELEASED"
AWAITING_APPROVAL = "AWAITING_APPROVAL"
HOLD = "HOLD_FOR_HUMAN_REVIEW"
REFUSED = "REFUSED"
NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
REJECTED = "REJECTED"
CHANGES_REQUESTED = "CHANGES_REQUESTED"


@dataclass
class GuardedResult:
    """What one guarded request returns to the caller or the UI."""

    thread_id: str
    status: str
    message: str = ""
    rule: str = ""
    route: str = ""
    tier: str = ""
    reasons: tuple[str, ...] = ()
    options: tuple[OptionGate, ...] = ()
    brief: str = ""
    issues: tuple[str, ...] = ()
    elapsed_ms: float = 0.0
    state: SquadState | None = field(default=None, repr=False)


def governance_checklist(state: SquadState) -> str:
    """One code-written line from the roster scan, so no figure in it comes from a model."""
    health = next((f.payload for f in state.findings if f.kind == "org_cliff_health"), None)
    if health is None:
        return ""
    summary = health["org_summary"]
    ledger = health.get("budget_status", {}).get("reconciliation_status", "not available")
    return (
        f"Governance checklist (Section 4): {summary['manager_inversion_count']} manager inversion(s), "
        f"{summary['stale_promo_band_count']} stale promotion band case(s) to audit. Ledger: {ledger}."
    )


class GuardedAdvisor:
    """Runs a request through the guardrails, the squad, the monitor and the approval gate."""

    def __init__(
        self,
        runtime_dir: Path | str | None = None,
        db_path: Path = DEFAULT_DB_PATH,
        memory: PartnerMemory | None = None,
        writer_fn: Callable[[SquadState], ExecutiveBrief] | None = None,
        tool_overrides: dict[str, Callable[..., Any]] | None = None,
        project_root: Path = PROJECT_ROOT,
        coordinator: MultiAgentCoordinator | None = None,
        engine: str = "stdlib",
    ) -> None:
        if engine not in ("stdlib", "langgraph", "auto"):
            raise ValueError(f"Unknown engine {engine!r}; expected 'stdlib', 'langgraph', or 'auto'")
        self.runtime_dir = Path(runtime_dir) if runtime_dir else DEFAULT_RUNTIME_DIR
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.project_root = project_root
        self.db_path = db_path
        self.memory = memory
        self.checkpointer = SqliteThreadCheckpointer(self.runtime_dir / "checkpoints.sqlite")
        self.coordinator = coordinator or MultiAgentCoordinator(
            db_path=db_path,
            memory=memory,
            writer_fn=writer_fn,
            tool_overrides=tool_overrides,
            checkpointer=self.checkpointer,
        )
        self.engine = ("langgraph" if langgraph_available() else "stdlib") if engine == "auto" else engine
        self._lg_squad: LangGraphSquad | None = None
        if self.engine == "langgraph":
            lg_sqlite = (self.runtime_dir / "langgraph.sqlite") if sqlite_saver_available() else None
            self._lg_squad = LangGraphSquad(coordinator=self.coordinator, sqlite_path=lg_sqlite)
        self.store = ApprovalStore(self.runtime_dir / "approvals.sqlite")
        self.audit = AuditLog(self.runtime_dir / "audit.jsonl")
        self.scope = load_scope(db_path)
        self.known_people = load_known_people(db_path)
        self.data_hash = hashlib.sha256(Path(db_path).read_bytes()).hexdigest()[:12]

    def default_partner(self) -> PartnerContext:
        return PartnerContext("HRBP_DEFAULT", tuple(self.scope))

    # ------------------------------------------------------------------ run

    def run(
        self,
        question: str,
        vp_org_code: str | None = None,
        job_family: str | None = None,
        partner: PartnerContext | None = None,
        thread_id: str | None = None,
    ) -> GuardedResult:
        started = time.perf_counter()
        partner = partner or self.default_partner()
        thread_id = thread_id or uuid.uuid4().hex[:12]

        def done(result: GuardedResult) -> GuardedResult:
            result.elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
            self.audit.record(
                thread_id, "result", status=result.status, route=result.route, tier=result.tier,
                reasons=list(result.reasons), elapsed_ms=result.elapsed_ms,
            )
            return result

        self.audit.record(
            thread_id, "request", partner_id=partner.partner_id, allowed_orgs=list(partner.allowed_orgs),
            vp_org_code=vp_org_code, job_family=job_family, question=question,
        )

        check = integrity.verify_manifest(self.project_root)
        self.audit.record(thread_id, "integrity", ok=check.ok, mismatches=list(check.mismatches))
        if not check.ok:
            return done(GuardedResult(
                thread_id, HOLD, route=ROUTE_HOLD, tier="BLOCKED", reasons=("integrity_mismatch",),
                message="The playbook does not match its recorded hash, so nothing was run. "
                + "; ".join(check.mismatches),
                issues=check.mismatches,
            ))

        verdict = screen_request(
            question, vp_org_code, job_family, partner, self.db_path, scope=self.scope,
            known_people=self.known_people,
        )
        self.audit.record(
            thread_id, "input_guard", decision=verdict.decision, rule=verdict.rule, matched=verdict.matched
        )
        if verdict.decision != ALLOW:
            status = REFUSED if verdict.decision == REFUSE else NEEDS_CLARIFICATION
            return done(GuardedResult(thread_id, status, message=verdict.message, rule=verdict.rule))
        if not vp_org_code and not is_policy_comparison(question):
            # The squad answers org briefs and two-sided policy comparisons. It never guesses an org.
            self.audit.record(thread_id, "scope_needed", reason="no org and not a comparison")
            return done(GuardedResult(
                thread_id, NEEDS_CLARIFICATION, rule="scope_needed",
                message="Choose a VP org for a brief, or ask how a playbook rule differs between two groups, "
                "such as new hires versus current staff. Orgs you cover: "
                + (", ".join(o for o in self.scope if o in partner.allowed_orgs) or "none") + ".",
            ))

        try:
            if self._lg_squad is not None:
                state, _ = self._lg_squad.run(
                    question, vp_org_code=vp_org_code, job_family=job_family, partner_id=partner.partner_id,
                    thread_id=thread_id, allowed_orgs=partner.allowed_orgs,
                )
                node_order = self._lg_squad.node_trace(thread_id)
                for node_name in node_order:
                    self.checkpointer.save(thread_id, node_name, state)
            else:
                state = self.coordinator.run(
                    question, vp_org_code=vp_org_code, job_family=job_family, partner_id=partner.partner_id,
                    thread_id=thread_id, allowed_orgs=partner.allowed_orgs,
                )
                node_order = [snap.node for snap in self.coordinator.checkpointer.history(thread_id)]
        except OrgAccessError as exc:
            self.audit.record(thread_id, "tool_scope", error=str(exc))
            return done(GuardedResult(thread_id, REFUSED, message=str(exc), rule="cross_org"))
        for call in state.tool_calls:
            self.audit.record(thread_id, "tool_call", agent=call["agent"], tool=call["tool"], args=call["args"])
        review = state.review
        self.audit.record(
            thread_id, "verifier", status=state.status, revisions=state.revisions,
            approved=bool(review and review.approved), issues=list(review.issues) if review else [],
            checked_numbers=review.checked_numbers if review else 0,
            checked_citations=review.checked_citations if review else 0, nodes=node_order,
        )

        guard_issues = check_brief(state)
        monitor_flags = review_trajectory(state, node_order)
        self.audit.record(thread_id, "output_guard", issues=list(guard_issues))
        self.audit.record(thread_id, "monitor", flags=list(monitor_flags), tool_calls=len(state.tool_calls))

        assessment = assess_risk(state, guard_issues, monitor_flags)
        self.audit.record(
            thread_id, "risk", tier=assessment.tier, route=assessment.route, reasons=list(assessment.reasons),
            options=[{"index": g.index, "role": g.role, "approvers": list(g.approvers)} for g in assessment.options],
        )

        base = dict(
            route=assessment.route, tier=assessment.tier, reasons=assessment.reasons, options=assessment.options,
            issues=tuple(review.issues if review else ()) + guard_issues + monitor_flags, state=state,
        )
        if assessment.route == ROUTE_AUTO:
            brief = self._release_text(state, thread_id, assessment, decision=None)
            self.audit.record(thread_id, "released", by="auto", chars=len(brief))
            return done(GuardedResult(thread_id, RELEASED, brief=brief, **base))

        self.store.open_request(thread_id, state, assessment, state.final_output)
        self.audit.record(thread_id, "gate_opened", route=assessment.route)
        if assessment.route == ROUTE_HOLD:
            return done(GuardedResult(
                thread_id, HOLD, brief=state.final_output,
                message="Held for a person. Nothing was released.", **base,
            ))
        return done(GuardedResult(
            thread_id, AWAITING_APPROVAL, brief=state.final_output,
            message="Verified and waiting for a decision. Nothing is released until a person approves.", **base,
        ))

    # --------------------------------------------------------------- decide

    def decide(
        self,
        thread_id: str,
        reviewer: PartnerContext,
        decision: str,
        option_index: int | None = None,
        acknowledged: tuple[str, ...] = (),
        reason_code: str = "",
        note: str = "",
    ) -> GuardedResult:
        """Applies one human decision to a waiting brief. Raises ApprovalError when the gate refuses it."""
        try:
            request = self.store.decide(
                thread_id, reviewer, decision, option_index, tuple(acknowledged), reason_code, note
            )
        except ApprovalError as exc:
            self.audit.record(
                thread_id, "decision_refused", reviewer=reviewer.partner_id, decision=decision, error=str(exc)
            )
            raise
        state = self.store.load_state(thread_id)
        record = request["decisions"][-1]
        state.approval = {
            "decision": decision, "reviewer": reviewer.partner_id, "option_index": option_index,
            "acknowledged": tuple(acknowledged), "reason_code": reason_code, "note": note.strip(),
            "decided_at": record["decided_at"],
        }
        self.audit.record(
            thread_id, "decision", reviewer=reviewer.partner_id, decision=decision, option_index=option_index,
            acknowledged=list(acknowledged), reason_code=reason_code, note=note.strip(),
        )
        assessment = RiskAssessment(request["tier"], request["route"], request["reasons"], request["options"])
        base = dict(
            route=assessment.route, tier=assessment.tier, reasons=assessment.reasons, options=assessment.options,
            state=state,
        )
        if decision == "approve":
            brief = self._release_text(state, thread_id, assessment, decision=state.approval)
            self.audit.record(thread_id, "released", by=reviewer.partner_id, chars=len(brief))
            return GuardedResult(thread_id, RELEASED, brief=brief, **base)

        if decision == "request_changes" and reason_code == "wrong_option_order" and option_index and self.memory:
            options = assessment.options
            if 1 <= option_index <= len(options) and state.vp_org_code:
                # Three sessions with the same edit make PartnerMemory propose a standing preference.
                self.memory.record_feedback(
                    reviewer.partner_id, state.vp_org_code, thread_id, "rank_last_option",
                    options[option_index - 1].role,
                )
                self.audit.record(thread_id, "feedback_recorded", key="rank_last_option",
                                  value=options[option_index - 1].role)
        status = REJECTED if decision == "reject" else CHANGES_REQUESTED
        return GuardedResult(
            thread_id, status, brief=state.final_output,
            message=f"{decision} by {reviewer.partner_id}: {reason_code}. Nothing was released.", **base,
        )

    # -------------------------------------------------------------- helpers

    def _release_text(
        self, state: SquadState, thread_id: str, assessment: RiskAssessment, decision: dict[str, Any] | None
    ) -> str:
        lines = [state.final_output]
        checklist = governance_checklist(state)
        if checklist:
            lines.append(checklist)
        if decision is not None:
            options = assessment.options
            index = decision.get("option_index")
            if options and index:
                chosen = options[index - 1]
                routed = "; ".join(decision.get("acknowledged") or ()) or "none needed"
                lines.append(
                    f"Decision record: {decision['reviewer']} advanced Option {index} ({chosen.role}) on "
                    f"{decision['decided_at']}. Sign-off routed to: {routed}. Those approvers still decide, and "
                    "the advisor changes no pay record."
                )
            else:
                lines.append(f"Decision record: {decision['reviewer']} approved release on {decision['decided_at']}.")
        elif "policy_answer_cited" in assessment.reasons:
            lines.append("Released without approval: a policy answer with every side cited.")
        else:
            lines.append("Released without approval: the brief costs no retention spend.")
        lines.append(AI_LABEL)
        playbook_hash = integrity.current_hashes(self.project_root)[integrity.PROTECTED_FILES[0]][:12]
        lines.append(f"Provenance: playbook sha256 {playbook_hash}, data sha256 {self.data_hash}, run {thread_id}.")
        return "\n".join(lines)

    def pending(self, partner: PartnerContext | None = None) -> list[dict[str, Any]]:
        return self.store.pending(partner)

    def trace(self, thread_id: str) -> dict[str, Any]:
        """Everything recorded for one run: audit lines and node timings."""
        return {
            "audit": self.audit.read(thread_id),
            "nodes": self.checkpointer.timings(thread_id),
            "chain": verify_chain(self.audit.path),
        }


# ---------------------------------------------------------------------- CLI


def _print_result(result: GuardedResult) -> None:
    print(f"[{result.status}] run {result.thread_id}  ({result.elapsed_ms:.0f} ms)")
    if result.rule:
        print(f"rule: {result.rule}")
    if result.message:
        print(result.message)
    if result.route:
        print(f"route: {result.route} (risk {result.tier}), reasons: {', '.join(result.reasons) or 'none'}")
    if result.brief:
        print()
        print(result.brief)
    if result.status == AWAITING_APPROVAL:
        print()
        for gate in result.options:
            needs = "; ".join(gate.approvers) or "the partner alone"
            fit = "inside" if gate.fits_budget else "above"
            print(f"  Option {gate.index}: ${gate.cost_usd:,.0f}, {fit} the remaining budget, sign-off: {needs}")
        print(f"\nDecide with: python3 -m src.guardrails.pipeline approve {result.thread_id} --option N --ack ROLE")
    if result.status == HOLD and result.issues:
        print("\nIssues:")
        for issue in result.issues:
            print(f"  - {issue}")


def _partner_from(args: argparse.Namespace, advisor: GuardedAdvisor) -> PartnerContext:
    orgs = tuple(o for o in (args.orgs or "").split(",") if o) or tuple(advisor.scope)
    return PartnerContext(args.partner, orgs)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m src.guardrails.pipeline",
        description="Run the compensation advisor behind its guardrails and approval gate.",
    )
    parser.add_argument("--runtime-dir", default=str(DEFAULT_RUNTIME_DIR), help="where the queue and logs live")
    parser.add_argument("--engine", choices=("auto", "stdlib", "langgraph"), default="auto",
                        help="graph engine (default: auto, using LangGraph when installed)")
    parser.add_argument("--partner", default="HRBP_DEFAULT", help="who is asking or deciding")
    parser.add_argument("--orgs", default="", help="comma-separated VP orgs the partner covers. Default: all")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="prepare a brief for a VP org or one job family")
    run_p.add_argument("vp_org_code")
    run_p.add_argument("job_family", nargs="?")
    run_p.add_argument("--question", default="")

    ask_p = sub.add_parser("ask", help="ask a playbook question")
    ask_p.add_argument("question")
    ask_p.add_argument("--org", default=None)

    sub.add_parser("pending", help="list briefs waiting for a person")
    sub.add_parser("triggers", help="count what sent briefs to a person and why reviewers sent them back")

    for name, text in (("approve", "release a waiting brief"), ("reject", "discard a waiting brief"),
                       ("changes", "send a waiting brief back")):
        dec = sub.add_parser(name, help=text)
        dec.add_argument("thread_id")
        dec.add_argument("--option", type=int, default=None)
        dec.add_argument("--ack", action="append", default=[], help="an approver whose sign-off you route")
        dec.add_argument("--reason", default="", help="reason code for reject or changes")
        dec.add_argument("--note", default="")

    trace_p = sub.add_parser("trace", help="print the audit lines of one run")
    trace_p.add_argument("thread_id")
    sub.add_parser("verify-log", help="check the audit log's hash chain")

    args = parser.parse_args(argv)
    advisor = GuardedAdvisor(runtime_dir=args.runtime_dir, engine=args.engine)
    partner = _partner_from(args, advisor)

    if args.command == "run":
        target = f"{args.vp_org_code}{' ' + args.job_family if args.job_family else ''}"
        question = args.question or f"Prepare the executive retention and offer brief for {target}."
        _print_result(advisor.run(question, args.vp_org_code, args.job_family, partner))
    elif args.command == "ask":
        _print_result(advisor.run(args.question, args.org, None, partner))
    elif args.command == "pending":
        rows = advisor.pending(partner)
        print(f"{len(rows)} brief(s) waiting")
        for row in rows:
            print(f"  {row['thread_id']}  {row['scope']:28s} {row['route']:18s} {', '.join(row['reasons'])}")
    elif args.command == "triggers":
        counts = advisor.store.summary()
        print(f"{counts['requests']} brief(s) reached a person")
        for signal, count in counts["review_triggers"].items():
            print(f"  {count:4d}  {signal}")
        if counts["override_reasons"]:
            print("Sent back or rejected, by reason code")
            for reason, count in sorted(counts["override_reasons"].items(), key=lambda item: (-item[1], item[0])):
                print(f"  {count:4d}  {reason}")
    elif args.command in ("approve", "reject", "changes"):
        decision = {"approve": "approve", "reject": "reject", "changes": "request_changes"}[args.command]
        try:
            _print_result(advisor.decide(
                args.thread_id, partner, decision, args.option, tuple(args.ack), args.reason, args.note
            ))
        except ApprovalError as exc:
            print(f"[GATE REFUSED] {exc}")
            return 1
    elif args.command == "trace":
        trace = advisor.trace(args.thread_id)
        for rec in trace["audit"]:
            extra = {k: v for k, v in rec.items() if k not in ("seq", "ts", "thread_id", "kind", "prev", "hash")}
            print(f"{rec['seq']:4d} {rec['ts'][11:23]} {rec['kind']:16s} {str(extra)[:150]}")
        print(f"chain ok: {trace['chain']['ok']} over {trace['chain']['records']} line(s)")
    elif args.command == "verify-log":
        chain = verify_chain(advisor.audit.path)
        print(f"chain ok: {chain['ok']}, lines: {chain['records']}, first bad line: {chain['first_bad_seq']}")
        return 0 if chain["ok"] else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
