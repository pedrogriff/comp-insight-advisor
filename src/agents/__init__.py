"""Multi-agent coordination, scoped tool registries, and review gates for Checkpoint 5.1."""

from __future__ import annotations

from typing import Any

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
    "OrgAccessError",
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


def __getattr__(name: str) -> Any:
    if name in __all__:
        from src.agents import coordinator

        return getattr(coordinator, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
