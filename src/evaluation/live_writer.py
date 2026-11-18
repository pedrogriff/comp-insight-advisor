"""Model-in-the-loop check: what does the verifier do with a real model's prose?

The scorecard runs on the code-written summary. This script sends the same 23
requests through the guarded advisor with the configured model writing the
summary, next to a code-written run of each, and records for every run:

- every draft, who wrote it, and what the verifier rejected it for;
- which text the brief ended with: the model's first draft, a model redraft,
  or the code-written summary after the model failed or could not be reached;
- whether the run ended with the same status and route as the code-written run.

It answers two questions. How often does a real model's prose pass the checks?
And before a demo, is the model reachable at all? A model that cannot be reached
is replaced by the code-written summary without any other sign, so check here.

From the repo root:
    python3 -m src.evaluation.live_writer --provider auto
    python3 -m src.evaluation.live_writer --provider ollama --only org_brief --repeats 3
    python3 -m src.evaluation.live_writer --provider auto --save experiments/final_evaluation/live_writer_run1.json
    python3 -m src.evaluation.live_writer --replay experiments/final_evaluation/live_writer_run1.json
"""

from __future__ import annotations

import argparse
from collections import Counter
import copy
import dataclasses
import json
from pathlib import Path
import platform
import re
import statistics
import sys
import tempfile
import time
from typing import Any, Callable

from src.agents.coordinator import MultiAgentCoordinator
from src.agents.state import ExecutiveBrief, SquadState, deterministic_verify_brief
from src.guardrails.evaluate import POLICY_QUESTIONS
from src.guardrails.input_guard import load_scope
from src.guardrails.output_guard import check_brief, check_model_prose
from src.guardrails.pipeline import GuardedAdvisor
from src.models.router import (
    DEFAULT_ENV_PATH,
    OUTCOME_AFTER_ERROR,
    OUTCOME_AFTER_REJECTION,
    OUTCOME_MODEL,
    OUTCOME_REJECTED,
    VALID_PROVIDERS,
    ModelRouter,
)

KINDS = ("org_brief", "cohort_brief", "policy_question")
Transport = Callable[[str, dict[str, str], dict[str, Any], float], dict[str, Any]]


def _reply(text: str) -> dict[str, Any]:
    """One answer in both shapes the router reads: an OpenAI-style choice and an Ollama message."""
    return {"choices": [{"message": {"content": text}}], "message": {"content": text}}


def _code_written_summary(payload: dict[str, Any]) -> str:
    return re.search(r"Verified summary baseline: (.*)", payload["messages"][1]["content"]).group(1)


def stand_in_copies(url: str, headers: dict[str, str], payload: dict[str, Any], timeout_s: float) -> dict[str, Any]:
    """A stand-in model that returns the code-written summary unchanged."""
    return _reply(_code_written_summary(payload))


def stand_in_invents(url: str, headers: dict[str, str], payload: dict[str, Any], timeout_s: float) -> dict[str, Any]:
    """A stand-in model that adds a figure no tool produced, on every try."""
    return _reply(_code_written_summary(payload) + " A further $9,999,999 sits in reserve.")


# Stand-in models for the scorecard and the tests. They take the place of the HTTP call, so the whole
# path from the prompt to the released brief runs with no network.
STAND_INS: dict[str, Transport] = {"copies_the_facts": stand_in_copies, "invents_a_figure": stand_in_invents}


def requests(scope: dict[str, Any]) -> list[dict[str, Any]]:
    """Every org brief, cohort brief and policy question, as the guardrail scorecard runs them."""
    out: list[dict[str, Any]] = []
    for org, families in scope.items():
        out.append({"kind": "org_brief", "label": org, "org": org, "family": None,
                    "question": f"Prepare the executive retention brief for {org}."})
        for family in families:
            out.append({"kind": "cohort_brief", "label": f"{org} {family}", "org": org, "family": family,
                        "question": f"Review retention options for {org} {family}."})
    for number, question in enumerate(POLICY_QUESTIONS, start=1):
        out.append({"kind": "policy_question", "label": f"policy question {number}", "org": None, "family": None,
                    "question": question})
    return out


def _ending(drafts: list[dict[str, Any]]) -> str:
    """Names the text a run ended with, from who wrote its last draft."""
    if not drafts:
        return "no_draft"
    last = drafts[-1]["by"]
    if last == OUTCOME_MODEL:
        return "model_first_draft" if len(drafts) == 1 else "model_redraft"
    return last


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    endings = Counter(row["ended_with"] for row in rows)
    kinds = Counter(issue.split(":", 1)[0] for row in rows for draft in row["drafts"] for issue in draft["rejected_for"])
    drafted = [row for row in rows if row["drafts"]]
    return {
        "runs": len(rows),
        "requests": len({row["request"] for row in rows}),
        "model_calls": sum(row["model_calls"] for row in rows),
        "model_first_draft_verified": sum(row["verified"] for row in rows if row["ended_with"] == "model_first_draft"),
        "model_redraft_verified": sum(row["verified"] for row in rows if row["ended_with"] == "model_redraft"),
        "code_written_after_rejection": endings[OUTCOME_AFTER_REJECTION],
        "code_written_after_error": endings[OUTCOME_AFTER_ERROR],
        "not_verified": sum(not row["verified"] for row in drafted),
        "same_end_as_code_written": sum(row["same_end_as_code_written"] for row in rows),
        "rejected_issue_kinds": dict(sorted(kinds.items())),
        "median_ms": round(statistics.median(row["elapsed_ms"] for row in rows), 1) if rows else 0.0,
        "code_written_median_ms": round(statistics.median(row["code_written_ms"] for row in rows), 1) if rows else 0.0,
    }


def run(
    provider: str = "auto",
    repeats: int = 1,
    only: tuple[str, ...] = (),
    limit: int | None = None,
    transport: Transport | None = None,
    env_path: Path | str | None = DEFAULT_ENV_PATH,
    timeout_s: float = 60.0,
    engine: str = "stdlib",
    progress: Callable[[dict[str, Any], int, int], None] | None = None,
) -> dict[str, Any]:
    """Runs every request with the code-written summary and with the model, and records both."""
    router = ModelRouter(provider=provider, env_path=env_path, timeout_s=timeout_s, transport=transport)
    active = router.resolve_provider()
    drafts: list[dict[str, Any]] = []

    def writer(state: SquadState) -> ExecutiveBrief:
        if drafts and state.revisions > 0 and state.review is not None:
            # The reviewer sent the last draft back. Record why, next to that draft.
            drafts[-1]["rejected_for"] = list(state.review.issues)
        before = len(router.call_log)
        brief = router.write_brief(state)
        for call in router.call_log[before:]:
            drafts.append({"by": call.outcome, "text": call.text, "rejected_for": list(call.problems)})
        return brief

    rows: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory() as tmp:
        code_advisor = GuardedAdvisor(runtime_dir=Path(tmp) / "code_written")
        live_advisor = GuardedAdvisor(runtime_dir=Path(tmp) / "live", writer_fn=writer, engine=engine)
        todo = [r for r in requests(code_advisor.scope) if not only or r["kind"] in only][:limit]
        total = len(todo) * repeats
        for request in todo:
            base = code_advisor.run(request["question"], request["org"], request["family"])
            for repeat in range(1, repeats + 1):
                drafts.clear()
                before = len(router.call_log)
                result = live_advisor.run(request["question"], request["org"], request["family"])
                calls = router.call_log[before:]
                review = result.state.review if result.state else None
                verified = bool(review and review.approved)
                if drafts and review is not None and not verified:
                    drafts[-1]["rejected_for"] = list(review.issues)
                rows.append({
                    "request": request["label"],
                    "kind": request["kind"],
                    "repeat": repeat,
                    "code_written": {"status": base.status, "route": base.route},
                    "status": result.status,
                    "route": result.route,
                    "same_end_as_code_written": (result.status, result.route) == (base.status, base.route),
                    "verified": verified,
                    "ended_with": _ending(drafts),
                    "model_calls": sum(
                        call.outcome in (OUTCOME_MODEL, OUTCOME_REJECTED, OUTCOME_AFTER_ERROR) for call in calls
                    ),
                    "errors": [call.note for call in calls if call.outcome == OUTCOME_AFTER_ERROR],
                    "drafts": copy.deepcopy(drafts),
                    "elapsed_ms": result.elapsed_ms,
                    "code_written_ms": base.elapsed_ms,
                })
                if progress is not None:
                    progress(rows[-1], len(rows), total)
    return {
        "about": "What the verifier did with a model's summary on each request. All data is synthetic. "
        "Written by python3 -m src.evaluation.live_writer.",
        "provider": active,
        "model": router.model_for_role("executive_synthesizer", active),
        "engine": engine,
        "python": platform.python_version(),
        "recorded_on": time.strftime("%Y-%m-%d", time.gmtime()),
        "repeats": repeats,
        "summary": summarize(rows),
        "runs": rows,
    }


def reverify(saved: dict[str, Any]) -> dict[str, Any]:
    """Checks a saved run against today's checks, with no model.

    Every model draft a saved run ended with must still pass the fact check, the verifier and the
    output check. Every model draft it rejected must still fail one of them. A change to a check that
    moves either count shows up here.
    """
    coordinator = MultiAgentCoordinator()
    by_label = {r["label"]: r for r in requests(load_scope(coordinator.db_path))}
    states: dict[str, SquadState] = {}
    out = {"accepted_checked": 0, "accepted_still_pass": 0, "rejected_checked": 0, "rejected_still_fail": 0,
           "changed": []}
    for row in saved["runs"]:
        request = by_label[row["request"]]
        if row["request"] not in states:
            states[row["request"]] = coordinator.run(
                request["question"], vp_org_code=request["org"], job_family=request["family"],
                thread_id=f"replay-{len(states)}",
            )
        clean = states[row["request"]]
        base = clean.draft
        if base is None:
            continue
        facts = "\n".join(ModelRouter._facts(base))
        for number, draft in enumerate(row["drafts"], start=1):
            if draft["by"] not in (OUTCOME_MODEL, OUTCOME_REJECTED):
                continue
            state = copy.copy(clean)
            state.draft = dataclasses.replace(base, summary=draft["text"])
            passes = (
                not check_model_prose(draft["text"], facts)
                and deterministic_verify_brief(state, coordinator.policy).approved
                and not check_brief(state)
            )
            accepted = draft["by"] == OUTCOME_MODEL and number == len(row["drafts"]) and row["verified"]
            out["accepted_checked" if accepted else "rejected_checked"] += 1
            if accepted and passes:
                out["accepted_still_pass"] += 1
            elif not accepted and not passes:
                out["rejected_still_fail"] += 1
            else:
                out["changed"].append(f"{row['request']} repeat {row['repeat']} draft {number}")
    return out


def _print_row(row: dict[str, Any], done: int, total: int) -> None:
    same = "same end as code-written" if row["same_end_as_code_written"] else "DIFFERENT END"
    note = f" [{row['errors'][0][:260]}]" if row["errors"] else ""
    print(f"[{done:>2}/{total}] {row['request']:<28} {row['ended_with']:<22} {row['status']:<22} {same}, "
          f"{row['elapsed_ms']:,.0f} ms{note}", flush=True)


def print_summary(result: dict[str, Any]) -> bool:
    """Prints the counts and returns True when the model was reachable and every run was verified."""
    s = result["summary"]
    runs = s["runs"]
    print(f"\nModel: {result['provider']} {result['model']}, {runs} runs over {s['requests']} requests, "
          f"{s['model_calls']} model calls")
    print(f"  the model's first draft passed every check:  {s['model_first_draft_verified']} of {runs}")
    print(f"  a model redraft passed after a rejection:    {s['model_redraft_verified']} of {runs}")
    print(f"  code-written summary after rejected drafts:  {s['code_written_after_rejection']} of {runs}")
    print(f"  code-written summary after a model error:    {s['code_written_after_error']} of {runs}")
    print(f"  not verified at the end:                     {s['not_verified']} of {runs}")
    print(f"  ended where the code-written run ended:      {s['same_end_as_code_written']} of {runs}")
    if s["rejected_issue_kinds"]:
        kinds = ", ".join(f"{name} {count}" for name, count in s["rejected_issue_kinds"].items())
        print(f"  why model drafts were rejected:              {kinds}")
    print(f"  median time: {s['median_ms']:,.0f} ms with the model, {s['code_written_median_ms']:,.0f} ms code-written")
    reached = s["code_written_after_error"] == 0
    sound = s["not_verified"] == 0 and s["same_end_as_code_written"] == runs
    if reached and sound:
        print("\nLIVE WRITER OK: the model answered every call, and every run ended verified.")
    elif not reached:
        print("\nLIVE WRITER CHECK: some calls ended with a model error, so code wrote those summaries. The "
              "bracketed errors above carry the provider's reason. Check the key in .env and the model name "
              "(python3 -m src.models.router --status).")
    else:
        print("\nLIVE WRITER CHECK: some runs ended unverified or on a different route than the code-written run.")
    return reached and sound


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m src.evaluation.live_writer",
        description="Measure what the verifier does with a real model's summary on every request.",
    )
    parser.add_argument("--provider", choices=VALID_PROVIDERS, default="auto")
    parser.add_argument("--repeats", type=int, default=1, help="runs per request (default 1)")
    parser.add_argument("--only", action="append", choices=KINDS, default=[], help="limit to one kind of request")
    parser.add_argument("--limit", type=int, default=None, help="stop after this many requests")
    parser.add_argument("--timeout", type=float, default=60.0, help="seconds to wait for one model call")
    parser.add_argument("--engine", choices=("stdlib", "langgraph", "auto"), default="stdlib")
    parser.add_argument("--save", metavar="PATH", help="write the run as JSON")
    parser.add_argument("--replay", metavar="PATH", help="check a saved run against today's verifier, no model")
    args = parser.parse_args(argv)

    if args.replay:
        saved = json.loads(Path(args.replay).read_text(encoding="utf-8"))
        check = reverify(saved)
        print_summary(saved)
        print(f"\nReplay: {check['accepted_still_pass']} of {check['accepted_checked']} model drafts the runs ended "
              f"with still pass, and {check['rejected_still_fail']} of {check['rejected_checked']} rejected ones "
              "still fail.")
        for line in check["changed"]:
            print(f"  changed: {line}")
        return 1 if check["changed"] else 0

    probe = ModelRouter(provider=args.provider)
    if probe.resolve_provider() == "offline":
        print("No live model is configured, so there is nothing to measure. Put a key in .env "
              "(OPENROUTER_API_KEY, GEMINI_API_KEY or OPENAI_API_KEY), or set OLLAMA_ENABLED=true, "
              "then run python3 -m src.models.router --status.")
        return 2
    result = run(args.provider, args.repeats, tuple(args.only), args.limit, timeout_s=args.timeout,
                 engine=args.engine, progress=_print_row)
    ok = print_summary(result)
    if args.save:
        out = Path(args.save)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
        print(f"saved {out}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
