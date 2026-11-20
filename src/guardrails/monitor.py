"""Runtime monitor: reads a finished run's trace and flags behavior outside its limits.

The tool executor and the review loop already stop single bad steps. The
monitor looks at the whole trajectory afterwards, from the tool-call log and
the checkpointed node order, and reports anything a correct run never does.
Any flag sends the run to a person instead of releasing it.

Flags:
- tool_outside_scope: an agent's logged call is not on its allowlist.
- org_outside_scope: a call names a VP org outside the partner's scope.
- duplicate_tool_call: the same agent repeated a call with the same arguments.
- tool_budget_exceeded: more calls than MAX_TOOL_CALLS.
- retrieval_attempts_exceeded: a lever was retrieved more than the cap allows.
- revision_cap_exceeded: more review rounds than the cap allows.
- unexpected_transition: the node order breaks the graph's edges.
- released_without_review: a brief is marked verified with no passing review.
- errors_recorded: a specialist reported an error.
- individual_data_in_state: the state the agents share names an employee. The
  tools hand over counts, averages and totals, so this never happens in a
  correct run. The flag gives a count and never repeats the identifier.
"""

from __future__ import annotations

import json

from src.agents import serialization
from src.agents.state import AGENT_TOOL_SCOPES, MAX_RETRIEVAL_ATTEMPTS, SquadState
from src.guardrails.output_guard import EMPLOYEE_ID_RE

# The largest measured run, the VP_CLOUD_AI org brief, makes 22 tool calls and writes 7 messages.
MAX_TOOL_CALLS = 40
MAX_MESSAGES = 20

ALLOWED_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "START": ("supervisor",),
    "supervisor": ("parallel_specialists", "executive_synthesizer"),
    "parallel_specialists": ("executive_synthesizer", "failover"),
    "executive_synthesizer": ("governance_reviewer",),
    "governance_reviewer": ("finalize", "executive_synthesizer", "escalate_unverified"),
    "finalize": (),
    "failover": (),
    "escalate_unverified": (),
}


def identifiers_in_shared_state(state: SquadState) -> int:
    """Counts employee and offer IDs in everything the agents pass on, apart from the partner's own request.

    The draft and the released text are left to the output check, which names the problem for the writer.
    """
    shared = serialization.encode(state)["fields"]
    for field in ("question", "draft", "review", "final_output"):
        shared.pop(field, None)
    return len(EMPLOYEE_ID_RE.findall(json.dumps(shared, default=str)))


def review_trajectory(state: SquadState, node_order: list[str] | None = None) -> tuple[str, ...]:
    """Returns the monitor's flags for one finished run, or an empty tuple."""
    flags: list[str] = []

    named = identifiers_in_shared_state(state)
    if named:
        flags.append(f"individual_data_in_state: {named} employee or offer identifier(s) in shared state, "
                     "and agents pass cohort figures only")

    seen: dict[tuple[str, str, str], int] = {}
    for call in state.tool_calls:
        agent, tool = call.get("agent", "?"), call.get("tool", "?")
        if tool not in AGENT_TOOL_SCOPES.get(agent, ()):
            flags.append(f"tool_outside_scope: {agent} called {tool}")
        args = call.get("args", {})
        if state.allowed_orgs is not None:
            orgs = [args["vp_org_code"]] if args.get("vp_org_code") else []
            orgs += [scope[0] for scope in args.get("cohorts") or []]
            for org in orgs:
                if org not in state.allowed_orgs:
                    flags.append(f"org_outside_scope: {agent} called {tool} for {org}")
        key = (agent, tool, json.dumps(args, sort_keys=True, default=str))
        seen[key] = seen.get(key, 0) + 1
    for (agent, tool, _), count in seen.items():
        if count > 1:
            flags.append(f"duplicate_tool_call: {agent} called {tool} {count} times with the same arguments")

    if len(state.tool_calls) > MAX_TOOL_CALLS:
        flags.append(f"tool_budget_exceeded: {len(state.tool_calls)} calls, limit {MAX_TOOL_CALLS}")
    if len(state.messages) > MAX_MESSAGES:
        flags.append(f"message_budget_exceeded: {len(state.messages)} messages, limit {MAX_MESSAGES}")

    for scope, grounded in state.grounded_by_cohort.items():
        for lever, attempts in grounded.get("retrieval_attempts_by_lever", {}).items():
            if attempts > MAX_RETRIEVAL_ATTEMPTS:
                flags.append(f"retrieval_attempts_exceeded: {scope} {lever} took {attempts} attempts")

    if state.revisions > state.max_revisions:
        flags.append(f"revision_cap_exceeded: {state.revisions} revisions, limit {state.max_revisions}")
    if state.status == "APPROVED" and not (state.review and state.review.approved):
        flags.append("released_without_review: status is APPROVED with no passing review")
    if state.errors:
        flags.append(f"errors_recorded: {len(state.errors)} specialist error(s)")

    if node_order:
        previous = "START"
        for node in node_order:
            if node not in ALLOWED_TRANSITIONS.get(previous, ()):
                flags.append(f"unexpected_transition: {previous} -> {node}")
            previous = node
        if previous == "finalize" and node_order.count("governance_reviewer") == 0:
            flags.append("released_without_review: finalize ran without governance_reviewer")

    return tuple(dict.fromkeys(flags))
