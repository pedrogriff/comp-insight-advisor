"""Risk routing and the human approval gate.

A verified brief is not a released brief. assess_risk() reads the verified
state and names one of four routes, and ApprovalStore keeps every brief that
waits for a person in SQLite, so a pending decision survives a restart.

Routes:
- AUTO_RELEASE (LOW): a cited policy answer, or a brief that costs no
  retention spend. Nobody has to approve it.
- PARTNER_APPROVAL (MEDIUM): the brief carries costed options that the
  partner owns. The partner picks an option, or sends the brief back.
- EXECUTIVE_SIGN_OFF (HIGH): at least one option needs a named approver from
  the playbook: the VP and the Head of Compensation for Tier 3 grants
  (Section 3), the VP for spend above the remaining proactive budget
  (Section 6.2), the calibration committee for level decisions (Section 6.3),
  or compensation governance for a policy conflict. Approving an option
  requires acknowledging each of that option's approvers.
- HOLD (BLOCKED): the verifier rejected the draft twice, a tool failed, the
  monitor or the output check flagged the run, or the playbook failed its
  hash check. A held brief can be discarded or rerun, never approved.

The gate records decisions. It grants nothing and changes no pay record.
"""

from __future__ import annotations

from contextlib import closing
import copy
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
from typing import Any

from src.agents import serialization
from src.agents.state import AGENT_TOOL_SCOPES, SquadState
from src.guardrails.input_guard import PartnerContext

ROUTE_AUTO = "AUTO_RELEASE"
ROUTE_PARTNER = "PARTNER_APPROVAL"
ROUTE_EXECUTIVE = "EXECUTIVE_SIGN_OFF"
ROUTE_HOLD = "HOLD"
TIER_BY_ROUTE = {ROUTE_AUTO: "LOW", ROUTE_PARTNER: "MEDIUM", ROUTE_EXECUTIVE: "HIGH", ROUTE_HOLD: "BLOCKED"}

DECISIONS = ("approve", "reject", "request_changes")
REASON_CODES = (
    "wrong_option_order",
    "missing_context",
    "disagree_with_evidence",
    "data_looks_wrong",
    "policy_question",
    "other",
)

SIGN_OFF_REASONS = (
    ("Tier 3", "tier3_grant"),
    ("above the remaining", "over_remaining_budget"),
    ("level decisions", "level_decision"),
)


class ApprovalError(ValueError):
    """Raised when a decision breaks a rule of the gate."""


@dataclass(frozen=True)
class OptionGate:
    """One option of a brief, with the approvers the playbook names for it."""

    index: int
    role: str
    cost_usd: float
    fits_budget: bool
    sign_offs: tuple[str, ...]
    approvers: tuple[str, ...]


@dataclass(frozen=True)
class RiskAssessment:
    tier: str
    route: str
    reasons: tuple[str, ...]
    options: tuple[OptionGate, ...]


def approvers_from_sign_off(sign_off: str) -> tuple[str, ...]:
    """'VP and Head of Compensation, Tier 3 grants (Section 3)' names two approvers."""
    who = sign_off.split(",", 1)[0]
    return tuple(part.strip() for part in re.split(r"\s+and\s+", who) if part.strip())


def _options_source(state: SquadState) -> list[dict[str, Any]]:
    if state.org_composition:
        return list(state.org_composition["options"])
    for finding in state.findings:
        if finding.kind == "cohort_front":
            return list(finding.payload["options"])
    return []


def option_gates(state: SquadState) -> tuple[OptionGate, ...]:
    """The brief's options in the order the brief lists them."""
    draft = state.draft
    if draft is None or not draft.option_lines or draft.mode == "cross_lever_policy":
        return ()
    by_role = {opt["role"]: opt for opt in _options_source(state)}
    gates: list[OptionGate] = []
    for line in draft.option_lines:
        role = next((r for r in by_role if f"({r})" in line), None)
        if role is None:
            continue
        opt = by_role[role]
        sign_offs = tuple(opt.get("sign_offs", []))
        approvers = tuple(dict.fromkeys(a for s in sign_offs for a in approvers_from_sign_off(s)))
        gates.append(
            OptionGate(
                index=len(gates) + 1,
                role=role,
                cost_usd=float(opt["first_year_cost_usd"]),
                fits_budget=bool(opt["fits_remaining_budget"]),
                sign_offs=sign_offs,
                approvers=approvers,
            )
        )
    return tuple(gates)


def assess_risk(
    state: SquadState,
    guard_issues: tuple[str, ...] = (),
    monitor_flags: tuple[str, ...] = (),
    integrity_ok: bool = True,
) -> RiskAssessment:
    """Names the route for one finished run. Every reason is a named proposition, checked in code."""
    blocked: list[str] = []
    if not integrity_ok:
        blocked.append("integrity_mismatch")
    if state.status == "HOLD_FOR_HUMAN_REVIEW":
        blocked.append("verifier_rejected_twice")
    if state.status == "FAILED_TOOL_ERROR":
        blocked.append("tool_failure")
    blocked += [f"output_guard:{issue.split(':', 1)[0]}" for issue in guard_issues]
    blocked += [f"monitor:{flag.split(':', 1)[0]}" for flag in monitor_flags]
    if state.status not in ("APPROVED", "HOLD_FOR_HUMAN_REVIEW", "FAILED_TOOL_ERROR"):
        blocked.append(f"unexpected_status:{state.status}")
    if blocked:
        return RiskAssessment("BLOCKED", ROUTE_HOLD, tuple(dict.fromkeys(blocked)), ())

    gates = option_gates(state)
    reasons: list[str] = []
    for gate in gates:
        for sign_off in gate.sign_offs:
            reasons += [code for marker, code in SIGN_OFF_REASONS if marker in sign_off]
    conflicts = [
        scope for scope, grounded in state.grounded_by_cohort.items() if grounded.get("policy_conflicts")
    ]
    if conflicts:
        reasons.append("policy_conflict")
        gates = tuple(
            OptionGate(g.index, g.role, g.cost_usd, g.fits_budget, g.sign_offs,
                       tuple(dict.fromkeys(g.approvers + ("Compensation governance",))))
            for g in gates
        )
    executive = bool(reasons)

    if gates:
        reasons.append("costed_options")
        if state.draft and state.draft.uncertainty_disclosures:
            reasons.append("thin_evidence")
        ledger = next(
            (
                f.payload.get("budget_status", {}).get("reconciliation_status", "")
                for f in state.findings
                if f.kind == "org_cliff_health"
            ),
            "",
        )
        if ledger and not ledger.startswith("Clean"):
            reasons.append("ledger_reconciliation_flag")

    if executive:
        route = ROUTE_EXECUTIVE
    elif gates:
        route = ROUTE_PARTNER
    else:
        route = ROUTE_AUTO
        reasons.append("policy_answer_cited" if state.draft and state.draft.mode == "cross_lever_policy"
                       else "no_retention_spend")
    return RiskAssessment(TIER_BY_ROUTE[route], route, tuple(dict.fromkeys(reasons)), gates)


def gate_payload(state: SquadState) -> dict[str, Any] | None:
    """What a paused run shows the person who decides, as plain JSON. None when nobody has to decide.

    The LangGraph engine passes this to interrupt(). The checks that can block a run come first,
    so a held run also pauses here instead of finishing.
    """
    from src.guardrails.monitor import review_trajectory
    from src.guardrails.output_guard import check_brief

    verified = state
    if state.status == "IN_PROGRESS" and state.review is not None and state.review.approved:
        # At the gate the reviewer has passed the draft, and finalize has not yet marked the run.
        verified = copy.copy(state)
        verified.status = "APPROVED"
    assessment = assess_risk(verified, check_brief(verified), review_trajectory(verified))
    if assessment.route == ROUTE_AUTO:
        return None
    return {
        "route": assessment.route,
        "tier": assessment.tier,
        "reasons": list(assessment.reasons),
        "scope": state.draft.scope if state.draft else state.vp_org_code,
        "options": [
            {"index": g.index, "role": g.role, "cost_usd": g.cost_usd, "fits_budget": g.fits_budget,
             "approvers": list(g.approvers)}
            for g in assessment.options
        ],
        "choices": list(DECISIONS),
    }


SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS approval_requests (
        thread_id TEXT PRIMARY KEY,
        created_at TEXT NOT NULL,
        partner_id TEXT NOT NULL,
        vp_org_code TEXT,
        scope TEXT NOT NULL,
        tier TEXT NOT NULL,
        route TEXT NOT NULL,
        reasons_json TEXT NOT NULL,
        options_json TEXT NOT NULL,
        brief_text TEXT NOT NULL,
        state_json TEXT NOT NULL,
        status TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS approval_decisions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        thread_id TEXT NOT NULL,
        decided_at TEXT NOT NULL,
        reviewer_id TEXT NOT NULL,
        decision TEXT NOT NULL,
        option_index INTEGER,
        reason_code TEXT NOT NULL,
        note TEXT NOT NULL,
        acknowledged_json TEXT NOT NULL
    )
    """,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ApprovalStore:
    """SQLite queue of briefs waiting for a person, and the record of what each person decided."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn, conn:
            for statement in SCHEMA:
                conn.execute(statement)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def open_request(
        self, thread_id: str, state: SquadState, assessment: RiskAssessment, brief_text: str
    ) -> dict[str, Any]:
        scope = state.draft.scope if state.draft else (state.vp_org_code or "unknown")
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT OR REPLACE INTO approval_requests VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    thread_id,
                    _now(),
                    state.partner_id,
                    state.vp_org_code,
                    scope,
                    assessment.tier,
                    assessment.route,
                    json.dumps(list(assessment.reasons)),
                    json.dumps([asdict(g) for g in assessment.options]),
                    brief_text,
                    serialization.dumps(state),
                    "PENDING",
                ),
            )
        return self.get(thread_id)

    def get(self, thread_id: str) -> dict[str, Any]:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT * FROM approval_requests WHERE thread_id = ?", (thread_id,)).fetchone()
            decisions = conn.execute(
                "SELECT * FROM approval_decisions WHERE thread_id = ? ORDER BY id", (thread_id,)
            ).fetchall()
        if row is None:
            raise ApprovalError(f"No approval request for thread {thread_id!r}")
        request = dict(row)
        request["reasons"] = tuple(json.loads(request.pop("reasons_json")))
        request["options"] = tuple(
            OptionGate(**{**o, "sign_offs": tuple(o["sign_offs"]), "approvers": tuple(o["approvers"])})
            for o in json.loads(request.pop("options_json"))
        )
        request["decisions"] = [
            {**dict(d), "acknowledged": tuple(json.loads(d["acknowledged_json"]))} for d in decisions
        ]
        return request

    def load_state(self, thread_id: str) -> SquadState:
        return serialization.loads(self.get(thread_id)["state_json"])

    def pending(self, partner: PartnerContext | None = None) -> list[dict[str, Any]]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT thread_id, created_at, partner_id, vp_org_code, scope, tier, route, reasons_json "
                "FROM approval_requests WHERE status = 'PENDING' ORDER BY created_at, thread_id"
            ).fetchall()
        out = []
        for row in rows:
            if partner is not None and row["vp_org_code"] and row["vp_org_code"] not in partner.allowed_orgs:
                continue
            item = dict(row)
            item["reasons"] = tuple(json.loads(item.pop("reasons_json")))
            out.append(item)
        return out

    def decide(
        self,
        thread_id: str,
        reviewer: PartnerContext,
        decision: str,
        option_index: int | None = None,
        acknowledged: tuple[str, ...] = (),
        reason_code: str = "",
        note: str = "",
    ) -> dict[str, Any]:
        """Records one human decision. Raises ApprovalError when the decision breaks a rule."""
        request = self.get(thread_id)
        if request["status"] != "PENDING":
            raise ApprovalError(f"Thread {thread_id!r} was already decided: {request['status']}")
        if decision not in DECISIONS:
            raise ApprovalError(f"Unknown decision {decision!r}. Use one of {', '.join(DECISIONS)}")
        if not reviewer.partner_id.strip() or reviewer.partner_id in AGENT_TOOL_SCOPES:
            raise ApprovalError("A decision needs a human reviewer. An agent cannot approve its own brief")
        if request["vp_org_code"] and request["vp_org_code"] not in reviewer.allowed_orgs:
            raise ApprovalError(f"{reviewer.partner_id} does not cover {request['vp_org_code']}")

        options: tuple[OptionGate, ...] = request["options"]
        if decision == "approve":
            if request["route"] == ROUTE_HOLD:
                raise ApprovalError("A held brief failed a check and cannot be released. Reject it or request changes")
            if options:
                if option_index is None or not 1 <= option_index <= len(options):
                    raise ApprovalError(f"Choose the option to advance, 1 to {len(options)}")
                missing = [a for a in options[option_index - 1].approvers if a not in acknowledged]
                if missing:
                    raise ApprovalError(
                        f"Option {option_index} needs sign-off from {', '.join(missing)}. Acknowledge each one"
                    )
            new_status = "APPROVED"
        else:
            if reason_code not in REASON_CODES:
                raise ApprovalError(f"Give a reason code, one of {', '.join(REASON_CODES)}")
            if reason_code == "other" and len(note.strip()) < 5:
                raise ApprovalError("Reason code 'other' needs a note")
            new_status = "REJECTED" if decision == "reject" else "CHANGES_REQUESTED"

        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO approval_decisions (thread_id, decided_at, reviewer_id, decision, option_index, "
                "reason_code, note, acknowledged_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (thread_id, _now(), reviewer.partner_id, decision, option_index, reason_code, note.strip(),
                 json.dumps(list(acknowledged))),
            )
            conn.execute("UPDATE approval_requests SET status = ? WHERE thread_id = ?", (new_status, thread_id))
        return self.get(thread_id)

    def summary(self) -> dict[str, Any]:
        """Counts by status, route and override reason, for the feedback loop."""
        with closing(self._connect()) as conn:
            by_status = dict(conn.execute("SELECT status, COUNT(*) FROM approval_requests GROUP BY 1").fetchall())
            by_route = dict(conn.execute("SELECT route, COUNT(*) FROM approval_requests GROUP BY 1").fetchall())
            by_reason = dict(
                conn.execute(
                    "SELECT reason_code, COUNT(*) FROM approval_decisions WHERE decision != 'approve' GROUP BY 1"
                ).fetchall()
            )
        decided = sum(v for k, v in by_status.items() if k != "PENDING")
        overrides = by_status.get("REJECTED", 0) + by_status.get("CHANGES_REQUESTED", 0)
        return {
            "requests": sum(by_status.values()),
            "by_status": by_status,
            "by_route": by_route,
            "override_reasons": by_reason,
            "override_rate": round(overrides / decided, 3) if decided else None,
        }
