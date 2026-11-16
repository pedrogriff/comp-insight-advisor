"""Typed state schemas, scoped tool execution, and deterministic brief verification.

Provides the shared SquadState message pool, append-only operator.add merge reducer,
per-thread state checkpointer, MCP-style role tool allowlists, and deterministic
Python verification gate used by the Checkpoint 5.1 five-node coordinator.
"""

from __future__ import annotations

from contextlib import closing
import copy
from dataclasses import asdict, dataclass, field
import json
import operator
from pathlib import Path
import re
from typing import Any, Callable

from src.memory.partner_memory import PartnerMemory
from src.planning.beam_validation import composable_cohort_front, plan_org_options
from src.planning.tot_planner import BEAM_WIDTH, choose_options, cohort_facts, plan_options, search
from src.retrieval.cross_lever import search_cross_lever, verify_comparison
from src.retrieval.embeddings import make_embedder
from src.retrieval.grounded_options import ground_options
from src.retrieval.policy_search import PLAYBOOK_PATH, PolicyRetriever
from src.tools.deterministic_analytics import (
    analyze_org_cliff_and_equity_health,
    analyze_reactive_offers_and_counters,
    connect_readonly,
)
from src.tools.evidence_check import assess_retention_evidence
from src.tools.intervention_fit import assess_intervention_fit
from src.tools.interview_search import NoteIndex

MAX_REVISIONS = 2
MAX_RETRIEVAL_ATTEMPTS = 2

# Scoped MCP-style tool allowlists per node. No specialist sees tools outside its domain.
AGENT_TOOL_SCOPES: dict[str, tuple[str, ...]] = {
    "supervisor": ("load_partner_memory", "list_org_cohorts", "compose_org_options"),
    "proactive_strategist": (
        "analyze_org_cliff_and_equity_health",
        "assess_intervention_fit",
        "plan_cohort_front",
    ),
    "reactive_analyst": (
        "analyze_reactive_offers_and_counters",
        "assess_retention_evidence",
        "search_exit_notes",
    ),
    "executive_synthesizer": (
        "ground_cohort_options",
        "compare_cross_lever_policies",
    ),
    "governance_reviewer": ("verify_brief",),
}

ALL_SPECIALIST_TOOLS: tuple[str, ...] = tuple(
    dict.fromkeys(tool for scope in AGENT_TOOL_SCOPES.values() for tool in scope)
)

MONEY_RE = re.compile(r"\$([0-9][0-9,]*(?:\.[0-9]+)?)")
PCT_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)%")
RATIO_RE = re.compile(r"\b([0-9]+)\s+of\s+([0-9]+)\s+(departures|declined offers)\b", re.I)


class ToolAccessError(PermissionError):
    """Raised when an agent attempts to invoke a tool outside its allowlist."""


class DuplicateToolCallError(RuntimeError):
    """Raised when an agent repeats an identical tool call in the same turn."""


class OrgAccessError(PermissionError):
    """Raised when a tool call names a VP org outside the requesting partner's scope."""


@dataclass(frozen=True)
class Finding:
    """One structured specialist observation appended to shared SquadState."""

    agent: str
    kind: str
    scope: str
    summary: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class InvestigationPlan:
    """Structured routing decision emitted by the supervisor node."""

    mode: str  # "org_retention_brief", "cohort_retention_brief", or "cross_lever_policy"
    vp_org_code: str | None
    job_family: str | None
    cohorts: tuple[tuple[str, str], ...]
    specialists: tuple[str, ...]
    proactive_task: str
    reactive_task: str
    synthesis_task: str
    ledger_budget_usd: float
    effective_budget_usd: float


@dataclass(frozen=True)
class DraftClaim:
    """One side-tagged claim in a cross-lever policy comparison."""

    side: str
    clause_id: str
    text: str


@dataclass(frozen=True)
class ExecutiveBrief:
    """Typed output written by executive_synthesizer and checked by governance_reviewer."""

    mode: str
    scope: str
    headline: str
    summary: str
    option_lines: tuple[str, ...]
    cited_clauses: tuple[str, ...]
    sign_offs: tuple[str, ...]
    uncertainty_disclosures: tuple[str, ...]
    memory_notes: tuple[str, ...]
    claims: tuple[DraftClaim, ...] = ()


@dataclass(frozen=True)
class ReviewVerdict:
    """Structured gate result returned by governance_reviewer."""

    approved: bool
    issues: tuple[str, ...]
    feedback: str
    checked_numbers: int
    checked_citations: int


@dataclass
class SquadState:
    """Shared state passed across graph nodes.

    Parallel specialists return partial updates whose list fields combine with
    operator.add in merge_parallel_updates(), matching Annotated[list, operator.add].
    """

    question: str
    vp_org_code: str | None = None
    job_family: str | None = None
    partner_id: str = "HRBP_DEFAULT"
    # VP orgs the requesting partner may see. The session sets it, never a model. None means no limit.
    allowed_orgs: tuple[str, ...] | None = None
    plan: InvestigationPlan | None = None
    active_preferences: list[dict[str, Any]] = field(default_factory=list)
    pending_preferences: list[dict[str, Any]] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    org_composition: dict[str, Any] | None = None
    grounded_by_cohort: dict[str, dict[str, Any]] = field(default_factory=dict)
    cross_lever_result: dict[str, Any] | None = None
    draft: ExecutiveBrief | None = None
    review: ReviewVerdict | None = None
    revisions: int = 0
    max_revisions: int = MAX_REVISIONS
    status: str = "IN_PROGRESS"
    final_output: str = ""
    # The human decision recorded at the approval gate, when one was needed.
    approval: dict[str, Any] | None = None
    errors: list[str] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class StepSnapshot:
    """Immutable per-step checkpoint entry."""

    step: int
    node: str
    status: str
    findings_count: int
    revisions: int
    messages_count: int
    state_copy: dict[str, Any]


class ThreadCheckpointer:
    """In-memory per-thread state checkpointer matching LangGraph's InMemorySaver."""

    def __init__(self) -> None:
        self._history: dict[str, list[StepSnapshot]] = {}

    def save(self, thread_id: str, node: str, state: SquadState) -> StepSnapshot:
        steps = self._history.setdefault(thread_id, [])
        snap = StepSnapshot(
            step=len(steps) + 1,
            node=node,
            status=state.status,
            findings_count=len(state.findings),
            revisions=state.revisions,
            messages_count=len(state.messages),
            state_copy=copy.deepcopy(asdict(state)),
        )
        steps.append(snap)
        return snap

    def history(self, thread_id: str) -> list[StepSnapshot]:
        return list(self._history.get(thread_id, []))

    def latest(self, thread_id: str) -> StepSnapshot | None:
        steps = self._history.get(thread_id, [])
        return steps[-1] if steps else None


def merge_parallel_updates(state: SquadState, updates: list[dict[str, Any]]) -> SquadState:
    """Applies parallel specialist partial updates using operator.add on append-only lists."""
    for upd in updates:
        if "findings" in upd:
            state.findings = operator.add(state.findings, list(upd["findings"]))
        if "messages" in upd:
            state.messages = operator.add(state.messages, list(upd["messages"]))
        if "tool_calls" in upd:
            state.tool_calls = operator.add(state.tool_calls, list(upd["tool_calls"]))
        if "errors" in upd:
            state.errors = operator.add(state.errors, list(upd["errors"]))
    return state


class ScopedToolExecutor:
    """MCP-style tool adapter enforcing role allowlists and duplicate-call guards."""

    def __init__(
        self,
        agent_name: str,
        tools: dict[str, Callable[..., Any]],
        allowed_tools: tuple[str, ...] | None = None,
        allowed_orgs: tuple[str, ...] | None = None,
    ) -> None:
        self.agent_name = agent_name
        self._tools = tools
        self.allowed_tools = allowed_tools if allowed_tools is not None else AGENT_TOOL_SCOPES[agent_name]
        self.allowed_orgs = allowed_orgs
        self._seen_calls: set[tuple[str, str]] = set()
        self.call_log: list[dict[str, Any]] = []

    def call(self, tool_name: str, **kwargs: Any) -> Any:
        if tool_name not in self.allowed_tools:
            raise ToolAccessError(
                f"{self.agent_name} cannot call {tool_name!r}; allowed tools: {list(self.allowed_tools)}"
            )
        if tool_name not in self._tools:
            raise ValueError(f"Unknown tool: {tool_name}")
        if self.allowed_orgs is not None:
            named_orgs = [kwargs["vp_org_code"]] if kwargs.get("vp_org_code") else []
            named_orgs += [scope[0] for scope in kwargs.get("cohorts") or []]
            for org in named_orgs:
                if org not in self.allowed_orgs:
                    raise OrgAccessError(
                        f"{self.agent_name} called {tool_name!r} for {org}, outside the partner's orgs "
                        f"{list(self.allowed_orgs)}"
                    )
        safe_args = {
            k: (f"<SquadState scope={v.vp_org_code} rev={v.revisions}>" if isinstance(v, SquadState) else v)
            for k, v in kwargs.items()
        }
        canonical = json.dumps(safe_args, sort_keys=True, default=str)
        sig = (tool_name, canonical)
        if sig in self._seen_calls:
            raise DuplicateToolCallError(
                f"{self.agent_name} repeated {tool_name}({canonical}) in the same turn"
            )
        self._seen_calls.add(sig)
        result = self._tools[tool_name](**kwargs)
        self.call_log.append({"agent": self.agent_name, "tool": tool_name, "args": safe_args})
        return result


def _list_org_cohorts(vp_org_code: str, db_path: Path) -> tuple[list[str], float]:
    with closing(connect_readonly(db_path)) as conn:
        families = [
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT job_family FROM org_roster_cashflows WHERE vp_org_code = ? ORDER BY 1",
                (vp_org_code,),
            ).fetchall()
        ]
        row = conn.execute(
            "SELECT proactive_remaining_usd FROM department_budgets WHERE vp_org_code = ?",
            (vp_org_code,),
        ).fetchone()
    return families, float(row[0]) if row else 0.0


def build_tool_map(
    db_path: Path,
    policy: PolicyRetriever,
    notes: NoteIndex,
    memory: PartnerMemory | None,
) -> dict[str, Callable[..., Any]]:
    """Constructs the canonical tool registry wrapped per specialist by ScopedToolExecutor."""

    def load_partner_memory(partner_id: str, vp_org_code: str) -> dict[str, Any]:
        if memory is None:
            return {"apply": [], "ask_partner": []}
        loaded = memory.load_for_session(partner_id, vp_org_code)
        return {
            "apply": [asdict(p) for p in loaded["apply"]],
            "ask_partner": [asdict(p) for p in loaded["ask_partner"]],
            "_raw_apply": loaded["apply"],
        }

    def list_org_cohorts(vp_org_code: str) -> dict[str, Any]:
        families, budget = _list_org_cohorts(vp_org_code, db_path)
        return {"vp_org_code": vp_org_code, "job_families": families, "ledger_budget_usd": budget}

    def plan_cohort_front(vp_org_code: str, job_family: str, budget_cap_usd: float | None = None) -> dict[str, Any]:
        facts = cohort_facts(vp_org_code, job_family, db_path)
        if budget_cap_usd is not None:
            facts = {**facts, "remaining_budget_usd": min(facts["remaining_budget_usd"], budget_cap_usd)}
        tree = search(facts, width=BEAM_WIDTH)
        front = composable_cohort_front(tree["nodes"])
        single = plan_options(vp_org_code, job_family, width=BEAM_WIDTH, db_path=db_path)
        if budget_cap_usd is not None and budget_cap_usd < facts["remaining_budget_usd"] + 1e-6:
            single_options = choose_options(tree)
        else:
            single_options = single["options"]
        return {
            "scope": f"{vp_org_code} {job_family}",
            "departures_total": facts["departures"]["total"],
            "declined_total": facts["declined"]["total"],
            "remaining_budget_usd": facts["remaining_budget_usd"],
            "evaluations": tree["evaluations"],
            "model_calls": tree["model_calls"],
            "front_count": len(front),
            "front": front,
            "options": single_options,
            "pruned_count": len(tree["pruned"]),
        }

    def compose_org_options(cohorts: list[tuple[str, str]], budget_usd: float) -> dict[str, Any]:
        raw = plan_org_options(cohorts, width=BEAM_WIDTH, budget_usd=budget_usd, db_path=db_path)
        facts_by_scope = {s: cohort_facts(*s, db_path) for s in cohorts}
        dep_total = sum(f["departures"]["total"] for f in facts_by_scope.values())
        dec_total = sum(f["declined"]["total"] for f in facts_by_scope.values())
        enriched_options = []
        for opt in raw["options"]:
            by_cohort = {
                fam: (" + ".join(f"{lv}:{sz}" for lv, sz in sub) or "no action")
                for (_, fam), sub in zip(cohorts, opt["plan"])
            }
            enriched_options.append({**opt, "by_cohort": by_cohort})
        return {
            **raw,
            "cohorts": cohorts,
            "departures_total": dep_total,
            "declined_total": dec_total,
            "options": enriched_options,
        }

    def search_exit_notes(vp_org_code: str, job_family: str, query: str = "") -> list[dict[str, Any]]:
        hits = notes.search(
            query,
            k=10,
            filters={"note_type": "exit", "vp_org_code": vp_org_code, "job_family": job_family},
        )
        return [{"note_id": n["note_id"], "themes": n["themes"], "text": n["text"]} for n in hits]

    def ground_cohort_options(vp_org_code: str, job_family: str) -> dict[str, Any]:
        grounded = ground_options(vp_org_code, job_family, policy=policy, notes=notes, db_path=db_path)
        attempts = {
            lever: min(
                MAX_RETRIEVAL_ATTEMPTS,
                1 + int(any(h.get("added_by") == "limit_check" for h in hits)),
            )
            for lever, hits in grounded["clauses"].items()
        }
        return {**grounded, "retrieval_attempts_by_lever": attempts}

    def compare_cross_lever_policies(question: str) -> dict[str, Any]:
        return search_cross_lever(policy, question)

    def verify_brief(state: SquadState) -> ReviewVerdict:
        return deterministic_verify_brief(state, policy)

    return {
        "load_partner_memory": load_partner_memory,
        "list_org_cohorts": list_org_cohorts,
        "compose_org_options": compose_org_options,
        "analyze_org_cliff_and_equity_health": lambda vp_org_code: analyze_org_cliff_and_equity_health(
            vp_org_code, db_path=db_path
        ),
        "assess_intervention_fit": lambda vp_org_code, job_family: assess_intervention_fit(
            vp_org_code, job_family, db_path=db_path
        ),
        "plan_cohort_front": plan_cohort_front,
        "analyze_reactive_offers_and_counters": lambda vp_org_code: analyze_reactive_offers_and_counters(
            vp_org_code, db_path=db_path
        ),
        "assess_retention_evidence": lambda vp_org_code, job_family: assess_retention_evidence(
            vp_org_code, job_family, db_path=db_path
        ),
        "search_exit_notes": search_exit_notes,
        "ground_cohort_options": ground_cohort_options,
        "compare_cross_lever_policies": compare_cross_lever_policies,
        "verify_brief": verify_brief,
    }


def _allowed_numbers_from_state(state: SquadState) -> tuple[set[float], set[float], set[tuple[int, int, str]]]:
    dollars: set[float] = set()
    percents: set[float] = set()
    ratios: set[tuple[int, int, str]] = set()

    if state.plan:
        dollars.add(round(float(state.plan.ledger_budget_usd), 2))
        dollars.add(round(float(state.plan.effective_budget_usd), 2))

    def _collect_numbers(obj: Any) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    if k.endswith("_usd") or "budget" in k or "cost" in k or "credit" in k or "gap" in k:
                        dollars.add(round(float(v), 2))
                    if k.endswith("_pct") or "rate" in k or "share" in k or "premium" in k:
                        percents.add(round(float(v), 1))
                elif isinstance(v, (list, tuple)) and k == "interval_95_pct" and len(v) == 2:
                    percents.add(round(float(v[0]), 1))
                    percents.add(round(float(v[1]), 1))
                else:
                    _collect_numbers(v)
        elif isinstance(obj, (list, tuple)):
            for item in obj:
                _collect_numbers(item)

    for f in state.findings:
        _collect_numbers(f.payload)
        if f.kind == "cohort_front":
            dep_total = int(f.payload["departures_total"])
            dec_total = int(f.payload["declined_total"])
            for opt in f.payload["options"]:
                ratios.add((int(opt["departures_addressed"]), dep_total, "departures"))
                ratios.add((int(opt["declined_addressed"]), dec_total, "declined offers"))

    if state.org_composition:
        _collect_numbers(state.org_composition)
        dep_total = int(state.org_composition["departures_total"])
        dec_total = int(state.org_composition["declined_total"])
        for opt in state.org_composition["options"]:
            ratios.add((int(opt["departures_addressed"]), dep_total, "departures"))
            ratios.add((int(opt["declined_addressed"]), dec_total, "declined offers"))
            if state.plan:
                rem = round(float(state.plan.effective_budget_usd) - float(opt["first_year_cost_usd"]), 2)
                if rem >= 0:
                    dollars.add(rem)

    cohort_tops = [
        f.payload["options"][0]["first_year_cost_usd"]
        for f in state.findings
        if f.kind == "cohort_front" and f.payload.get("options")
    ]
    if len(cohort_tops) >= 2:
        standalone_sum = round(sum(float(x) for x in cohort_tops), 2)
        dollars.add(standalone_sum)
        if state.plan and standalone_sum > state.plan.effective_budget_usd:
            dollars.add(round(standalone_sum - state.plan.effective_budget_usd, 2))

    for g in state.grounded_by_cohort.values():
        _collect_numbers(g)
        for hits in g.get("clauses", {}).values():
            for h in hits:
                for m in MONEY_RE.finditer(h["text"]):
                    dollars.add(round(float(m.group(1).replace(",", "")), 2))
                for m in PCT_RE.finditer(h["text"]):
                    percents.add(round(float(m.group(1)), 1))

    if state.cross_lever_result:
        for group in state.cross_lever_result.get("groups", []):
            for h in group.get("clauses", []):
                for m in MONEY_RE.finditer(h["text"]):
                    dollars.add(round(float(m.group(1).replace(",", "")), 2))
                for m in PCT_RE.finditer(h["text"]):
                    percents.add(round(float(m.group(1)), 1))
        for h in state.cross_lever_result.get("shared", []):
            for m in MONEY_RE.finditer(h["text"]):
                dollars.add(round(float(m.group(1).replace(",", "")), 2))
            for m in PCT_RE.finditer(h["text"]):
                percents.add(round(float(m.group(1)), 1))

    return dollars, percents, ratios


def deterministic_verify_brief(
    state: SquadState,
    policy: PolicyRetriever | None = None,
) -> ReviewVerdict:
    """Checks all currency figures, percentages, coverage ratios, citations, and disclosures."""
    draft = state.draft
    if draft is None:
        return ReviewVerdict(
            approved=False,
            issues=("missing_draft: executive_synthesizer produced no ExecutiveBrief",),
            feedback="Produce a complete ExecutiveBrief object with grounded figures and clause IDs.",
            checked_numbers=0,
            checked_citations=0,
        )

    issues: list[str] = []
    checked_numbers = 0
    checked_citations = 0

    if draft.mode == "cross_lever_policy":
        if not state.cross_lever_result:
            issues.append("missing_cross_lever_search: no search_cross_lever result in state")
        else:
            pol = policy or PolicyRetriever(make_embedder("hashing"), path=PLAYBOOK_PATH)
            verdict = verify_comparison(
                state.cross_lever_result,
                [{"side": c.side, "cited": c.clause_id, "text": c.text} for c in draft.claims],
                pol,
            )
            checked_citations = len(draft.claims)
            checked_numbers = sum(
                len(MONEY_RE.findall(c.text)) + len(PCT_RE.findall(c.text)) for c in draft.claims
            )
            if not verdict["ok"]:
                for prob in verdict["problems"]:
                    issues.append(f"cross_lever_violation: {prob}")
                for ms in verdict["missing_sides"]:
                    issues.append(f"cross_lever_missing_side: {ms}")
        if not draft.cited_clauses:
            issues.append("missing_citations: cross-lever brief cites zero playbook clause IDs")
        feedback = "; ".join(issues) if issues else "Approved: every side cites its own population rule."
        return ReviewVerdict(
            approved=not issues,
            issues=tuple(issues),
            feedback=feedback,
            checked_numbers=checked_numbers,
            checked_citations=checked_citations,
        )

    dollars, percents, ratios = _allowed_numbers_from_state(state)
    full_text = "\n".join([draft.headline, draft.summary, *draft.option_lines, *draft.uncertainty_disclosures])

    for m in MONEY_RE.finditer(full_text):
        checked_numbers += 1
        val = round(float(m.group(1).replace(",", "")), 2)
        if val not in dollars:
            issues.append(f"unverified_currency: ${m.group(1)} does not match any tool output figure")

    for m in PCT_RE.finditer(full_text):
        checked_numbers += 1
        val = round(float(m.group(1)), 1)
        if val not in percents:
            issues.append(f"unverified_percentage: {m.group(1)}% does not match any tool output percentage")

    for m in RATIO_RE.finditer(full_text):
        checked_numbers += 1
        pair = (int(m.group(1)), int(m.group(2)), m.group(3).lower())
        if pair not in ratios:
            issues.append(
                f"unverified_coverage_ratio: '{m.group(0)}' does not match any evaluated option coverage"
            )

    available_clauses = {
        h["id"]
        for g in state.grounded_by_cohort.values()
        for hits in g.get("clauses", {}).values()
        for h in hits
    } | {
        item["clause"]["id"]
        for g in state.grounded_by_cohort.values()
        for item in g.get("checklist", [])
        if item.get("clause")
    }
    for cid in draft.cited_clauses:
        checked_citations += 1
        if cid not in available_clauses:
            issues.append(f"unverified_citation: clause {cid!r} was not retrieved in grounded_by_cohort")
    if not draft.cited_clauses and draft.option_lines:
        issues.append("missing_citations: retention brief must cite retrieved playbook clauses")

    convergent_evidence = [
        f.payload
        for f in state.findings
        if f.kind == "retention_evidence" and f.payload.get("pattern") == "CONVERGENT"
    ]
    needs_uncertainty = any(
        bool(ev.get("uncertainty_disclosure_required")) for ev in convergent_evidence
    )
    convergent_scopes = {
        f"{ev['scope']['vp_org_code']} {ev['scope']['job_family']}" for ev in convergent_evidence
    }
    thin_departures = any(
        f.kind == "intervention_fit"
        and f.scope in convergent_scopes
        and f.payload.get("flags", {}).get("thin_driver_evidence")
        for f in state.findings
    )
    if (needs_uncertainty or thin_departures) and not draft.uncertainty_disclosures:
        issues.append(
            "missing_uncertainty_disclosure: tool flags require explicit sample-size or interval disclosure"
        )

    expected_signoffs: set[str] = set()
    options_source = (
        state.org_composition["options"]
        if state.org_composition
        else next(
            (f.payload["options"] for f in state.findings if f.kind == "cohort_front"),
            [],
        )
    )
    for opt in options_source:
        expected_signoffs.update(opt.get("sign_offs", []))

    evaluated_triples = {
        (int(o["departures_addressed"]), int(o["declined_addressed"]), round(float(o["first_year_cost_usd"]), 2))
        for o in options_source
    }
    for line in draft.option_lines:
        dep = re.search(r"\b([0-9]+)\s+of\s+[0-9]+\s+departures\b", line, re.I)
        dec = re.search(r"\b([0-9]+)\s+of\s+[0-9]+\s+declined offers\b", line, re.I)
        cost = MONEY_RE.search(line)
        if not (dep and dec and cost):
            continue
        triple = (int(dep.group(1)), int(dec.group(1)), round(float(cost.group(1).replace(",", "")), 2))
        if triple not in evaluated_triples:
            issues.append(
                f"option_figure_mismatch: '{line.split(':', 1)[0]}' pairs {triple[0]} departures, {triple[1]} "
                f"declined offers and ${cost.group(1)}, which no single evaluated option has"
            )
    missing_signoffs = sorted(expected_signoffs - set(draft.sign_offs))
    if missing_signoffs:
        issues.append(f"missing_sign_offs: brief omitted required sign-offs {missing_signoffs}")

    feedback = (
        "Replace every unverified figure with exact tool-output values, attach retrieved clause IDs, "
        "include all required sign-offs, and add uncertainty disclosures where flagged: " + "; ".join(issues)
        if issues
        else "Approved: all currency figures, percentages, coverage ratios, citations, and disclosures verified."
    )
    return ReviewVerdict(
        approved=not issues,
        issues=tuple(issues),
        feedback=feedback,
        checked_numbers=checked_numbers,
        checked_citations=checked_citations,
    )
