"""LangGraph engine for the five-agent squad.

coordinator.py walks the squad's graph in standard-library Python. This
module builds the same graph as a LangGraph StateGraph and reuses the
coordinator's node methods unchanged, so both engines produce the same brief:

    START -> supervisor -> Send() to proactive_strategist and reactive_analyst
          -> join_specialists -> executive_synthesizer -> governance_reviewer
          -> approval_gate -> finalize -> END

- Parallel fan-out. The supervisor's conditional edge returns one Send() per
  specialist. Their findings, messages, tool calls and errors land in list
  channels declared as Annotated[list, operator.add].
- Review loop. governance_reviewer writes a route flag and the conditional
  edge reads it: back to executive_synthesizer while revisions stay under
  the cap, on to the approval gate when verified, or to escalate_unverified.
- Approval gate. When a gate function says a person must decide, the node
  calls interrupt() with the decision payload. The checkpointer keeps the
  paused run, in SQLite when a file path is given, and
  Command(resume=decision) continues it, also after a restart.

State crosses the graph as plain JSON values (see serialization.py), so any
checkpointer can store it and the typed SquadState comes back exact.

LangGraph is optional. Without it, importing this module still works,
langgraph_available() returns False, and MultiAgentCoordinator.run() is the
engine. SquadNodes holds the node wrappers and needs no LangGraph, which is
how the tests check them on a machine without the package.

From the repo root, with LangGraph installed:
    python3 -m src.agents.graph VP_CLOUD_AI
    python3 -m src.agents.graph VP_CLOUD_AI --gate
"""

from __future__ import annotations

import importlib.util
import operator
from pathlib import Path
import sqlite3
import sys
from typing import Annotated, Any, Callable, TypedDict

from src.agents import serialization
from src.agents.coordinator import MultiAgentCoordinator
from src.agents.state import MAX_REVISIONS, SquadState, merge_parallel_updates

GateFn = Callable[[SquadState], "dict[str, Any] | None"]
SPECIALIST_ORDER = {"proactive_strategist": 0, "reactive_analyst": 1}


def langgraph_available() -> bool:
    """True when the langgraph package can be imported."""
    try:
        return importlib.util.find_spec("langgraph") is not None
    except (ImportError, ValueError):
        return False


def sqlite_saver_available() -> bool:
    """True when langgraph-checkpoint-sqlite can be imported."""
    if not langgraph_available():
        return False
    try:
        return importlib.util.find_spec("langgraph.checkpoint.sqlite") is not None
    except (ImportError, ValueError):
        return False


class GraphState(TypedDict, total=False):
    """Channels of the LangGraph state. Every value is plain JSON."""

    squad: dict[str, Any]
    findings: Annotated[list, operator.add]
    messages: Annotated[list, operator.add]
    tool_calls: Annotated[list, operator.add]
    errors: Annotated[list, operator.add]
    node_trace: Annotated[list, operator.add]
    route: str


def _agent_rank(text_or_agent: str) -> int:
    for agent, rank in SPECIALIST_ORDER.items():
        if text_or_agent.startswith(agent):
            return rank
    return len(SPECIALIST_ORDER)


class SquadNodes:
    """The graph's nodes as functions from a state dict to a partial update. Needs no LangGraph."""

    def __init__(self, coordinator: MultiAgentCoordinator, gate: GateFn | None = None) -> None:
        self.coordinator = coordinator
        self.gate = gate

    @staticmethod
    def load(state: dict[str, Any]) -> SquadState:
        return serialization.decode(state["squad"])

    @staticmethod
    def dump(squad: SquadState) -> dict[str, Any]:
        return serialization.encode(squad)

    def supervisor(self, state: dict[str, Any]) -> dict[str, Any]:
        squad = self.coordinator.supervisor_node(self.load(state))
        return {"squad": self.dump(squad), "node_trace": ["supervisor"]}

    def fan_out_targets(self, state: dict[str, Any]) -> list[str]:
        return self.coordinator.fan_out_from_supervisor(self.load(state))

    def _specialist(self, state: dict[str, Any], node: Callable[[SquadState], dict[str, Any]]) -> dict[str, Any]:
        update = node(self.load(state))
        return {
            "findings": [serialization.encode(f) for f in update["findings"]],
            "messages": list(update["messages"]),
            "tool_calls": [serialization.encode(c) for c in update["tool_calls"]],
            "errors": list(update["errors"]),
        }

    def proactive_strategist(self, state: dict[str, Any]) -> dict[str, Any]:
        return self._specialist(state, self.coordinator.proactive_strategist_node)

    def reactive_analyst(self, state: dict[str, Any]) -> dict[str, Any]:
        return self._specialist(state, self.coordinator.reactive_analyst_node)

    def join_specialists(self, state: dict[str, Any]) -> dict[str, Any]:
        """Fan-in. Merges the list channels into the squad, proactive first, as the other engine does."""
        squad = self.load(state)
        findings = sorted((serialization.decode(f) for f in state.get("findings", [])),
                          key=lambda f: _agent_rank(f.agent))
        tool_calls = sorted((serialization.decode(c) for c in state.get("tool_calls", [])),
                            key=lambda c: _agent_rank(c.get("agent", "")))
        messages = sorted(state.get("messages", []), key=_agent_rank)
        errors = sorted(state.get("errors", []), key=_agent_rank)
        squad = merge_parallel_updates(
            squad, [{"findings": findings, "messages": messages, "tool_calls": tool_calls, "errors": errors}]
        )
        return {
            "squad": self.dump(squad),
            "route": self.coordinator.route_after_specialists(squad),
            "node_trace": ["parallel_specialists"],
        }

    def executive_synthesizer(self, state: dict[str, Any]) -> dict[str, Any]:
        squad = self.coordinator.executive_synthesizer_node(self.load(state))
        return {"squad": self.dump(squad), "node_trace": ["executive_synthesizer"]}

    def governance_reviewer(self, state: dict[str, Any]) -> dict[str, Any]:
        squad = self.coordinator.governance_reviewer_node(self.load(state))
        route = self.coordinator.route_after_review(squad)
        if route == "revise":
            squad.revisions += 1
        return {"squad": self.dump(squad), "route": route, "node_trace": ["governance_reviewer"]}

    def approval_gate(self, state: dict[str, Any]) -> dict[str, Any]:
        """Pauses for a person when the gate function returns a payload. Reruns from the top on resume."""
        squad = self.load(state)
        payload = self.gate(squad) if self.gate is not None else None
        if payload is not None:
            from langgraph.types import interrupt

            decision = interrupt(payload)
            squad.approval = dict(decision) if isinstance(decision, dict) else {"decision": decision}
        return {"squad": self.dump(squad)}

    def finalize(self, state: dict[str, Any]) -> dict[str, Any]:
        squad = self.coordinator.finalize_node(self.load(state))
        return {"squad": self.dump(squad), "node_trace": ["finalize"]}

    def failover(self, state: dict[str, Any]) -> dict[str, Any]:
        squad = self.coordinator.failover_node(self.load(state))
        return {"squad": self.dump(squad), "node_trace": ["failover"]}

    def escalate_unverified(self, state: dict[str, Any]) -> dict[str, Any]:
        squad = self.coordinator.escalate_unverified_node(self.load(state))
        return {"squad": self.dump(squad), "node_trace": ["escalate_unverified"]}


def drive_without_langgraph(nodes: SquadNodes, initial: SquadState) -> tuple[SquadState, list[str]]:
    """Walks the node wrappers in the graph's order with plain Python.

    It mirrors the edges build_graph() declares, including the list channels, and exists so the
    wrappers, the encoding and the route flags can be tested where LangGraph is not installed.
    """
    state: dict[str, Any] = {"squad": nodes.dump(initial), "findings": [], "messages": [], "tool_calls": [],
                             "errors": [], "node_trace": []}

    def apply(update: dict[str, Any]) -> None:
        for key, value in update.items():
            if key in ("findings", "messages", "tool_calls", "errors", "node_trace"):
                state[key] = operator.add(state[key], value)
            else:
                state[key] = value

    apply(nodes.supervisor(state))
    targets = nodes.fan_out_targets(state)
    if targets != ["executive_synthesizer"]:
        sent = {"squad": state["squad"]}
        updates = [getattr(nodes, target)(sent) for target in reversed(targets)]  # any arrival order must work
        for update in updates:
            apply(update)
        apply(nodes.join_specialists(state))
        if state["route"] == "failover":
            apply(nodes.failover(state))
            return nodes.load(state), state["node_trace"]
    while True:
        apply(nodes.executive_synthesizer(state))
        apply(nodes.governance_reviewer(state))
        if state["route"] == "revise":
            continue
        if state["route"] == "escalate_unverified":
            apply(nodes.escalate_unverified(state))
            return nodes.load(state), state["node_trace"]
        apply(nodes.approval_gate(state))
        apply(nodes.finalize(state))
        return nodes.load(state), state["node_trace"]


def build_graph(coordinator: MultiAgentCoordinator, checkpointer: Any = None, gate: GateFn | None = None) -> Any:
    """Compiles the squad as a LangGraph StateGraph."""
    from langgraph.graph import END, START, StateGraph

    try:
        from langgraph.types import Send
    except ImportError:  # older releases kept Send in constants
        from langgraph.constants import Send

    nodes = SquadNodes(coordinator, gate)
    builder = StateGraph(GraphState)
    for name in ("supervisor", "proactive_strategist", "reactive_analyst", "join_specialists",
                 "executive_synthesizer", "governance_reviewer", "approval_gate", "finalize", "failover",
                 "escalate_unverified"):
        builder.add_node(name, getattr(nodes, name))

    def fan_out(state: dict[str, Any]) -> Any:
        targets = nodes.fan_out_targets(state)
        if targets == ["executive_synthesizer"]:
            return "executive_synthesizer"
        return [Send(target, {"squad": state["squad"]}) for target in targets]

    builder.add_edge(START, "supervisor")
    builder.add_conditional_edges(
        "supervisor", fan_out, ["proactive_strategist", "reactive_analyst", "executive_synthesizer"]
    )
    builder.add_edge("proactive_strategist", "join_specialists")
    builder.add_edge("reactive_analyst", "join_specialists")
    builder.add_conditional_edges(
        "join_specialists",
        lambda state: state["route"],
        {"failover": "failover", "executive_synthesizer": "executive_synthesizer"},
    )
    builder.add_edge("executive_synthesizer", "governance_reviewer")
    builder.add_conditional_edges(
        "governance_reviewer",
        lambda state: state["route"],
        {"finalize": "approval_gate", "revise": "executive_synthesizer", "escalate_unverified": "escalate_unverified"},
    )
    builder.add_edge("approval_gate", "finalize")
    builder.add_edge("finalize", END)
    builder.add_edge("failover", END)
    builder.add_edge("escalate_unverified", END)
    return builder.compile(checkpointer=checkpointer)


def make_checkpointer(sqlite_path: Path | str | None = None) -> Any:
    """A SQLite checkpointer when a path is given, so a paused run survives a restart. In memory otherwise."""
    if sqlite_path is not None:
        from langgraph.checkpoint.sqlite import SqliteSaver

        Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)
        return SqliteSaver(sqlite3.connect(str(sqlite_path), check_same_thread=False))
    try:
        from langgraph.checkpoint.memory import InMemorySaver
    except ImportError:  # older releases call it MemorySaver
        from langgraph.checkpoint.memory import MemorySaver as InMemorySaver
    return InMemorySaver()


class LangGraphSquad:
    """Runs the squad on LangGraph. run() takes the same arguments as MultiAgentCoordinator.run().

    Give every run its own thread_id. The list channels append, so a reused thread would add a
    second run's findings to the first.
    """

    def __init__(
        self,
        coordinator: MultiAgentCoordinator | None = None,
        gate: GateFn | None = None,
        sqlite_path: Path | str | None = None,
        checkpointer: Any = None,
    ) -> None:
        if not langgraph_available():
            raise RuntimeError(
                "LangGraph is not installed. Run pip install -r requirements.txt, or use "
                "MultiAgentCoordinator.run(), which needs no packages."
            )
        self.coordinator = coordinator or MultiAgentCoordinator()
        self.checkpointer = checkpointer if checkpointer is not None else make_checkpointer(sqlite_path)
        self.graph = build_graph(self.coordinator, self.checkpointer, gate)

    @staticmethod
    def _config(thread_id: str) -> dict[str, Any]:
        return {"configurable": {"thread_id": thread_id}}

    def run(
        self,
        question: str,
        vp_org_code: str | None = None,
        job_family: str | None = None,
        partner_id: str = "HRBP_DEFAULT",
        max_revisions: int = MAX_REVISIONS,
        thread_id: str = "default-thread",
        allowed_orgs: tuple[str, ...] | None = None,
    ) -> tuple[SquadState, dict[str, Any] | None]:
        """Returns the squad state and, when the run paused at the approval gate, the decision payload."""
        initial = self.coordinator.initial_state(
            question, vp_org_code, job_family, partner_id, max_revisions, allowed_orgs
        )
        self.graph.invoke({"squad": serialization.encode(initial)}, self._config(thread_id))
        return self.snapshot(thread_id)

    def snapshot(self, thread_id: str) -> tuple[SquadState, dict[str, Any] | None]:
        """The thread's latest state, and the pending decision payload if it is paused."""
        snap = self.graph.get_state(self._config(thread_id))
        squad = serialization.decode(snap.values["squad"])
        pending = None
        if snap.next:
            pending = {}
            for task in snap.tasks:
                for item in getattr(task, "interrupts", ()) or ():
                    pending = item.value
        return squad, pending

    def resume(self, thread_id: str, decision: dict[str, Any]) -> SquadState:
        """Continues a paused run with the person's decision."""
        from langgraph.types import Command

        self.graph.invoke(Command(resume=decision), self._config(thread_id))
        return self.snapshot(thread_id)[0]

    def node_trace(self, thread_id: str) -> list[str]:
        return list(self.graph.get_state(self._config(thread_id)).values.get("node_trace", []))


if __name__ == "__main__":
    cli_args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not langgraph_available():
        raise SystemExit("LangGraph is not installed. Run: pip install -r requirements.txt")
    org = cli_args[0] if cli_args else "VP_CLOUD_AI"
    family = cli_args[1] if len(cli_args) >= 2 else None
    gate_fn = None
    if "--gate" in sys.argv[1:]:
        from src.guardrails.approval import gate_payload

        gate_fn = gate_payload
    runner = LangGraphSquad(gate=gate_fn)
    out_state, waiting = runner.run(
        f"Prepare an executive retention brief for {org}{(' ' + family) if family else ''}.",
        vp_org_code=org, job_family=family, thread_id="cli-run",
    )
    if waiting is not None:
        print(f"Paused at the approval gate: route {waiting.get('route')}, reasons {waiting.get('reasons')}")
        out_state = runner.resume("cli-run", {"decision": "approve", "reviewer": "CLI_DEMO", "option_index": 1})
        print("Resumed with Command(resume=...).")
    print(out_state.final_output)
    print(f"\n[telemetry] engine=langgraph status={out_state.status} tool_calls={len(out_state.tool_calls)} "
          f"messages={len(out_state.messages)} revisions={out_state.revisions} nodes={runner.node_trace('cli-run')}")
