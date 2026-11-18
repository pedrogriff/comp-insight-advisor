"""One scorecard for the whole advisor: every offline result the final report cites.

Eight questions, each answered by a count on cases with a known right answer:

1. Can a model answer from the raw rows, or does it need the tools? Two recorded
   model runs, read from the files they left in experiments/.
2. Does the squad beat one agent that holds every tool? One org, one shared budget.
3. Does retrieval find the right clause for the right population?
4. Does the beam find what an exhaustive search finds?
5. Do the guardrails stop what they should and nothing else?
6. Where does each request end, and how often does a person have to look?
7. Can a model's paragraph change a figure or a route? Stand-in models, no network.
8. What do the controls cost in time? Timing changes from machine to machine, so
   it sits apart and no test compares it.

Nothing here calls a model. From the repo root:
    python3 -m src.evaluation.scorecard            # recompute, print, compare with the committed file
    python3 -m src.evaluation.scorecard --write    # recompute and rewrite experiments/final_evaluation/
    python3 -m src.evaluation.scorecard --json
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
import re
import sys
from typing import Any

from src.agents.coordinator import compare_single_vs_squad
from src.evaluation import live_writer
from src.guardrails.evaluate import run_all as run_guardrail_scorecard
from src.planning.beam_validation import COHORTS, VP_CLOUD_AI_COHORTS, validate_cohort_beam, validate_org_scaling
from src.retrieval.cross_lever import evaluate_cross_lever
from src.retrieval.embeddings import make_embedder
from src.retrieval.policy_search import PolicyRetriever, evaluate as evaluate_policy_search
from src.tools.deterministic_analytics import analyze_org_cliff_and_equity_health
from src.tools.interview_search import evaluate as evaluate_interview_search

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
OUT_DIR = PROJECT_ROOT / "experiments" / "final_evaluation"
JSON_PATH = OUT_DIR / "scorecard.json"
MD_PATH = OUT_DIR / "scorecard.md"
SAVED_SCORES = PROJECT_ROOT / "experiments" / "policy_retrieval" / "nomic-embed-text.json"
SAVED_ROUTER_SCORES = PROJECT_ROOT / "experiments" / "policy_retrieval" / "nomic-embed-text-router.json"
ROWS_EXPERIMENT = PROJECT_ROOT / "experiments" / "rows_vs_summary"
DRIFT_EXPERIMENT = PROJECT_ROOT / "experiments" / "compa_ratio_drift"
VOLATILE = ("timing",)
SPLITS = {"dev": "tuning", "heldout": "held_out"}

# A whole number in a model's answer: not part of a name such as rating_4, a percentage or a decimal.
_ANSWER_INT = re.compile(r"(?<![\w.])\d+(?![\w%]|[.,]\d)")


def _pair(text: str) -> tuple[int, int]:
    left, right = text.split("/")
    return int(left), int(right)


def _add(*fractions: str) -> str:
    pairs = [_pair(f) for f in fractions]
    return f"{sum(p[0] for p in pairs)}/{sum(p[1] for p in pairs)}"


def _data_rows(path: Path) -> int:
    with path.open(newline="", encoding="utf-8") as handle:
        return sum(1 for _ in csv.reader(handle)) - 1


# ------------------------------------------------------------ 1. a model alone


def model_alone() -> dict[str, Any]:
    """Two experiments that ran a real model, scored again from the files they left."""
    truth = analyze_org_cliff_and_equity_health("VP_CLOUD_AI")["org_summary"]
    want = [truth["cliff_count_gt_15pct"], truth["high_performer_cliff_count"]]
    answers: dict[str, list[list[int]]] = {"rows": [], "summary": []}
    for path in sorted((ROWS_EXPERIMENT / "runs").glob("*.txt")):
        found = [int(n) for n in _ANSWER_INT.findall(path.read_text(encoding="utf-8"))]
        answers[path.stem.rsplit("_", 1)[0]].append(found[:2])
    with (DRIFT_EXPERIMENT / "results" / "summary_by_setup.csv").open(newline="", encoding="utf-8") as handle:
        drift = {row["setup"]: row for row in csv.DictReader(handle)}
    text, tool = drift["text"], drift["tool"]
    return {
        "question": "Can a model answer from the raw rows, or does it need the tools?",
        "counting": {
            "source": "experiments/rows_vs_summary, Gemini 3.5 Flash in Google AI Studio, Oct 19, 2026",
            "rows_given": _data_rows(ROWS_EXPERIMENT / "org_a_rows.csv"),
            "right_answer": want,
            "reading_the_rows": {
                "runs": len(answers["rows"]),
                "right": sum(a == want for a in answers["rows"]),
                "answers": answers["rows"],
            },
            "reading_the_tool_summary": {
                "runs": len(answers["summary"]),
                "right": sum(a == want for a in answers["summary"]),
            },
        },
        "dividing": {
            "source": f"experiments/compa_ratio_drift, {text['provider']} {text['model']}, Oct 22, 2026",
            "employees": _data_rows(DRIFT_EXPERIMENT / "sample.csv"),
            "in_text": {
                "runs": int(text["runs"]),
                "exact_median": int(text["exact_median"]),
                "exact_min": int(text["exact_min"]),
                "exact_max": int(text["exact_max"]),
                "worst_miss": float(text["worst_miss"]),
            },
            "with_a_divide_tool": {
                "runs": int(tool["runs"]),
                "exact_median": int(tool["exact_median"]),
                "exact_min": int(tool["exact_min"]),
                "tokens_per_run_median": int(tool["tokens_per_run_median"]),
                "seconds_median": float(tool["seconds_median"]),
            },
        },
    }


# ------------------------------------------------- 2. one agent or the squad


def one_agent_or_squad() -> dict[str, Any]:
    comp = compare_single_vs_squad()
    one, squad = comp["single_agent"], comp["multi_agent_squad"]
    return {
        "question": "Does the squad beat one agent that holds every tool?",
        "org": comp["vp_org_code"],
        "budget_usd": int(comp["ledger_budget_usd"]),
        "one_agent": {
            "tools_in_one_prompt": one["tools_exposed_per_turn"],
            "tool_calls": one["total_tool_calls"],
            "cost_usd": int(one["combined_first_year_cost_usd"]),
            "fits_budget": one["fits_org_budget"],
            "over_budget_usd": int(one["budget_overrun_usd"]),
            "departures_addressed": one["departures_addressed"],
        },
        "squad": {
            "max_tools_per_node": squad["max_tools_per_node"],
            "tool_calls": squad["total_tool_calls"],
            "cost_usd": int(squad["combined_first_year_cost_usd"]),
            "fits_budget": squad["fits_org_budget"],
            "headroom_usd": int(squad["budget_headroom_usd"]),
            "departures_addressed": squad["departures_addressed"],
            "departures_total": squad["departures_total"],
            "declined_addressed": squad["declined_addressed"],
            "declined_total": squad["declined_total"],
            "joint_plans_priced": squad["joint_evaluations"],
            "joint_plans_possible": squad["exhaustive_joint_plans"],
        },
        "note": "No model runs in this comparison. Both sides call the same tools. The squad's gain comes "
        "from composing the two teams under one budget, a step the one-agent baseline leaves out.",
    }


# ---------------------------------------------------------------- 3. retrieval


def retrieval() -> dict[str, Any]:
    saved = make_embedder(f"saved:{SAVED_SCORES}")
    configs = {"keyword": "bm25 rules", "dense": f"dense {saved.name}", "hybrid": f"hybrid {saved.name}"}
    reports = {name: evaluate_policy_search(saved, split=split) for split, name in SPLITS.items()}
    policy: dict[str, Any] = {
        "cases": {name: len(report["cases"]) for name, report in reports.items()},
        "embedding_model": "nomic-embed-text through Ollama, replayed from experiments/policy_retrieval/",
    }
    for mode, config in configs.items():
        rows = {name: report["configs"][config] for name, report in reports.items()}
        hit = {name: row["hit_at_3"] for name, row in rows.items()}
        empty = {name: row["abstained_correctly"] for name, row in rows.items()}
        policy[mode] = {
            "right_clause_in_top_3": {**hit, "all": _add(*hit.values())},
            "returned_nothing_when_uncovered": {**empty, "all": _add(*empty.values())},
            "wrong_population_first": sum(row["wrong_population_first"] for row in rows.values()),
        }

    cross: dict[str, Any] = {}
    retrievers = {
        "keyword": PolicyRetriever(make_embedder(None)),
        "hybrid": PolicyRetriever(make_embedder(f"saved:{SAVED_ROUTER_SCORES}")),
    }
    for mode, retriever in retrievers.items():
        cross[mode] = {}
        for split, name in SPLITS.items():
            report = evaluate_cross_lever(retriever, split=split)
            cross.setdefault("cases", {})[name] = report["questions"]
            cross[mode][name] = {
                "one_query": report["configs"]["one query, no filter"],
                "one_query_per_side": report["configs"]["one query per side"],
            }

    notes = evaluate_interview_search()
    return {
        "question": "Does retrieval find the right clause for the right population?",
        "policy_questions": policy,
        "cross_lever_comparisons": cross,
        "interview_notes": {"cases": len(notes["cases"]), **notes["summary"]["expanded"]},
    }


# ----------------------------------------------------------------- 4. planning


def planning() -> dict[str, Any]:
    exhaustive = {"plans": 0, "pareto_plans": 0, "critic_reviews": 0}
    widths: dict[str, dict[str, int]] = {}
    for org, family in COHORTS:
        result = validate_cohort_beam(org, family)
        full = result["exhaustive"]
        exhaustive["plans"] += full["plans_evaluated"]
        exhaustive["pareto_plans"] += len(full["pareto"])
        exhaustive["critic_reviews"] += full["model_calls"]
        for width, row in result["by_width"].items():
            tally = widths.setdefault(str(width), {
                "options_right": 0, "options": 0, "pareto_plans_missed": 0, "budget_levels_wrong": 0,
                "budget_levels": 0, "plans_priced": 0, "critic_reviews": 0,
            })
            tally["options"] += len(full["options"])
            tally["options_right"] += len(full["options"]) - len(row["missed_options"])
            tally["pareto_plans_missed"] += len(row["missed_pareto"])
            tally["budget_levels_wrong"] += row["budget_option_misses"]
            tally["budget_levels"] += row["budget_thresholds_tested"]
            tally["plans_priced"] += row["evaluations"]
            tally["critic_reviews"] += row["model_calls"]
    chosen = widths["3"]
    orgs: dict[str, Any] = {}
    for label, scopes in (("one_org_two_teams", VP_CLOUD_AI_COHORTS), ("three_teams", COHORTS)):
        result = validate_org_scaling(scopes)
        factored, flat = result["factored_by_width"][3], result["flat_by_cap"][40]
        orgs[label] = {
            "joint_plans_possible": result["exhaustive_plans"],
            "per_team_beams_then_composition": {
                "plans_priced": factored["evaluations"],
                "options_match_exhaustive": factored["options_match"],
                "pareto_front_matches_exhaustive": factored["pareto_match"],
            },
            "one_flat_beam_capped_at_40": {
                "plans_priced": flat["evaluations"],
                "options_match_exhaustive": flat["options_match"],
            },
        }
    return {
        "question": "Does the beam find what an exhaustive search finds?",
        "cohorts": [f"{org} {family}" for org, family in COHORTS],
        "exhaustive": exhaustive,
        "by_beam_width": widths,
        "fewer_critic_reviews_at_width_3_pct": round(
            100 * (1 - chosen["critic_reviews"] / exhaustive["critic_reviews"]), 1
        ),
        "org_planning": orgs,
        "note": "A critic review is one plan a model critic would be asked to judge. No model runs here. "
        "The count sizes what a model critic would cost.",
    }


# ------------------------------------------------- 5 and 6. guardrails, routing


def guardrails(report: dict[str, Any]) -> dict[str, Any]:
    keys = ("cases", "decisions_right", "benign", "false_refusals", "violations", "missed_violations")
    splits = {name: {key: row[key] for key in keys} for name, row in report["request_screen"].items()}
    contain, verifier, monitor, gate = (report[k] for k in ("containment", "verifier", "monitor", "gate"))
    return {
        "question": "Do the guardrails stop what they should and nothing else?",
        "request_screen": {
            "splits": splits,
            "all_splits": {key: sum(row[key] for row in splits.values()) for key in keys},
        },
        "containment": {
            "violations_past_the_screen": contain["violations_past_the_screen"],
            "contained": contain["violations_past_the_screen"] - contain["not_contained"],
            "where_they_ended": contain["outcomes"],
        },
        "verifier_and_output_check": {
            "clean_briefs": verifier["verified_briefs"],
            "clean_briefs_passed": verifier["clean_briefs_passed"],
            "faults_seeded": verifier["faults_seeded"],
            "faults_rejected": verifier["faults_rejected"],
            "by_fault": verifier["by_fault"],
            "missed": verifier["missed"],
        },
        "runtime_monitor": {
            "flags_on_a_clean_run": monitor["clean_run_flags"],
            "trace_faults_seeded": monitor["seeded_faults"],
            "trace_faults_flagged": monitor["faults_flagged"],
        },
        "approval_gate": {
            "invalid_decisions": gate["invalid_decisions"],
            "invalid_decisions_refused": gate["invalid_decisions_refused"],
            "waiting_brief_survived_restart": gate["pending_survived_restart"],
            "valid_approval_released": gate["valid_approval_released"],
            "audit_chain_intact": gate["audit_chain_ok"],
            "changed_log_line_found": gate["tampered_line_found"],
        },
    }


def routing(report: dict[str, Any]) -> dict[str, Any]:
    row = report["routing"]
    return {
        "question": "Where does each request end, and how often does a person have to look?",
        "requests": row["requests"],
        "by_kind": row["routes"],
        "released_without_a_person": row["released_without_a_person"],
        "waited_for_a_person": row["needs_a_person"],
        "escalation_rate_pct": round(100 * row["escalation_rate"], 1),
        "held": row["held"],
    }


def model_prose() -> dict[str, Any]:
    """What the checks do with a model's paragraph, shown with stand-in models and no network."""
    out: dict[str, Any] = {"question": "Can a model's paragraph change a figure or a route?"}
    for name, transport in live_writer.STAND_INS.items():
        summary = live_writer.run("ollama", transport=transport, env_path=None)["summary"]
        out[name] = {
            "runs": summary["runs"],
            "first_draft_accepted": summary["model_first_draft_verified"],
            "drafts_rejected": sum(summary["rejected_issue_kinds"].values()),
            "ended_on_the_code_written_paragraph": summary["code_written_after_rejection"],
            "not_verified": summary["not_verified"],
            "same_route_as_the_code_written_run": summary["same_end_as_code_written"],
        }
    out["note"] = ("Stand-in models take the place of the HTTP call. python3 -m src.evaluation.live_writer "
                   "runs the same requests with a real model.")
    return out


def timing(report: dict[str, Any]) -> dict[str, Any]:
    latency, row = report["latency"], report["routing"]
    return {
        "note": "Measured on the machine that wrote this file, with the code-written summary and no model. "
        "It changes from machine to machine, so no test compares it.",
        "squad_alone_median_ms": latency["squad_alone_median_ms"],
        "guarded_median_ms": latency["guarded_median_ms"],
        "controls_add_median_ms": latency["controls_add_median_ms"],
        "refusal_median_ms": latency["refusal_median_ms"],
        "all_requests_median_ms": row["median_ms"],
        "all_requests_slowest_ms": row["max_ms"],
    }


# --------------------------------------------------------------- the scorecard


def build() -> dict[str, Any]:
    report = run_guardrail_scorecard()
    card = {
        "about": "Final evaluation scorecard for comp-insight-advisor. All data is synthetic. Rewrite it with "
        "python3 -m src.evaluation.scorecard --write.",
        "model_alone": model_alone(),
        "one_agent_or_squad": one_agent_or_squad(),
        "retrieval": retrieval(),
        "planning": planning(),
        "guardrails": guardrails(report),
        "routing": routing(report),
        "model_prose": model_prose(),
        "timing": timing(report),
    }
    return json.loads(json.dumps(card))


def stable(card: dict[str, Any]) -> dict[str, Any]:
    """The scorecard without the parts that change from machine to machine."""
    return {key: value for key, value in card.items() if key not in VOLATILE}


def differences(old: Any, new: Any, path: str = "") -> list[str]:
    """Paths where two scorecards disagree, for a readable failure message."""
    if isinstance(old, dict) and isinstance(new, dict):
        out: list[str] = []
        for key in sorted(set(old) | set(new)):
            where = f"{path}.{key}" if path else str(key)
            if key not in old or key not in new:
                out.append(f"{where}: only in the {'new' if key not in old else 'committed'} scorecard")
            else:
                out += differences(old[key], new[key], where)
        return out
    return [] if old == new else [f"{path}: committed {old!r}, now {new!r}"]


def _of(fraction: str) -> str:
    left, right = _pair(fraction)
    return f"{left} of {right}"


def _usd(value: int) -> str:
    return f"${value:,.0f}"


def headline(card: dict[str, Any]) -> list[tuple[str, str]]:
    """The results in sentences. The final report quotes these, and a test holds it to them."""
    count, divide = card["model_alone"]["counting"], card["model_alone"]["dividing"]
    one, squad = card["one_agent_or_squad"]["one_agent"], card["one_agent_or_squad"]["squad"]
    policy, cross = card["retrieval"]["policy_questions"], card["retrieval"]["cross_lever_comparisons"]
    plan, guard, route = card["planning"], card["guardrails"], card["routing"]
    beam, full = plan["by_beam_width"]["3"], plan["exhaustive"]
    two, three = plan["org_planning"]["one_org_two_teams"], plan["org_planning"]["three_teams"]
    screen, fresh = guard["request_screen"]["all_splits"], guard["request_screen"]["splits"]["held_out_2"]
    contain, check = guard["containment"], guard["verifier_and_output_check"]
    monitor, gate = guard["runtime_monitor"], guard["approval_gate"]
    copies, invents = card["model_prose"]["copies_the_facts"], card["model_prose"]["invents_a_figure"]
    uncovered = _pair(policy["keyword"]["returned_nothing_when_uncovered"]["all"])[1]
    missed_kinds = sorted({miss.split(" on ")[0] for miss in check["missed"]})
    missed_note = (
        "are invented percentages that match a figure elsewhere in the tool output"
        if missed_kinds == ["invented_percentage"]
        else "are of these kinds: " + ", ".join(missed_kinds)
    )
    composed = [team["per_team_beams_then_composition"]["options_match_exhaustive"] for team in (two, three)]
    composed_note = "matched the exhaustive options both times" if all(composed) else (
        f"matched the exhaustive options in {sum(composed)} of {len(composed)} cases"
    )

    def sides(mode: str, config: str) -> str:
        return _of(cross[mode]["held_out"][config]["sides_answered"])

    return [
        ("A model alone, counting",
         f"Given {count['rows_given']} rows, the model got a two-number count right in "
         f"{count['reading_the_rows']['right']} of {count['reading_the_rows']['runs']} runs. Given the tool's "
         f"summary, it was right in {count['reading_the_tool_summary']['right']} of "
         f"{count['reading_the_tool_summary']['runs']}."),
        ("A model alone, dividing",
         f"Dividing in text, the model matched the stored compa-ratio for a median of "
         f"{divide['in_text']['exact_median']} of {divide['employees']} employees. With a divide tool it matched "
         f"{divide['with_a_divide_tool']['exact_median']} of {divide['employees']}."),
        ("Composing teams under one budget",
         f"The one-agent baseline prices each team alone, and its plans add up to {_usd(one['cost_usd'])}, "
         f"{_usd(one['over_budget_usd'])} over the {_usd(card['one_agent_or_squad']['budget_usd'])} budget. The "
         f"squad's joint plan costs {_usd(squad['cost_usd'])} and addresses {squad['departures_addressed']} of "
         f"{squad['departures_total']} departures and {squad['declined_addressed']} of {squad['declined_total']} "
         "declined offers."),
        ("Policy retrieval",
         f"The right clause is in the top 3 for {_of(policy['keyword']['right_clause_in_top_3']['all'])} questions "
         f"with keyword search, {_of(policy['dense']['right_clause_in_top_3']['all'])} with dense search and "
         f"{_of(policy['hybrid']['right_clause_in_top_3']['all'])} with hybrid search. On the {uncovered} questions "
         f"the playbook does not cover, keyword search returned nothing for "
         f"{_of(policy['keyword']['returned_nothing_when_uncovered']['all'])}, dense search for "
         f"{_of(policy['dense']['returned_nothing_when_uncovered']['all'])} and hybrid search for "
         f"{_of(policy['hybrid']['returned_nothing_when_uncovered']['all'])}."),
        ("Comparisons across populations",
         f"On held-out comparisons, one query per side answers {sides('hybrid', 'one_query_per_side')} sides with "
         f"hybrid search, against {sides('hybrid', 'one_query')} for a single query. With keyword search it is "
         f"{sides('keyword', 'one_query_per_side')} against {sides('keyword', 'one_query')}."),
        ("Planning, one team",
         f"Beam width 3 returned {beam['options_right']} of {beam['options']} options and "
         f"{full['pareto_plans'] - beam['pareto_plans_missed']} of {full['pareto_plans']} Pareto plans, and "
         f"stayed right at {beam['budget_levels'] - beam['budget_levels_wrong']} of {beam['budget_levels']} "
         f"budget levels. It plans {beam['critic_reviews']} critic reviews against {full['critic_reviews']} for "
         f"exhaustive search, {plan['fewer_critic_reviews_at_width_3_pct']}% fewer."),
        ("Planning, several teams",
         f"Per-team beams plus composition priced {two['per_team_beams_then_composition']['plans_priced']} of "
         f"{two['joint_plans_possible']:,} joint plans for two teams and "
         f"{three['per_team_beams_then_composition']['plans_priced']} of {three['joint_plans_possible']:,} for "
         f"three, and {composed_note}."),
        ("Request screen",
         f"The screen refused {screen['false_refusals']} of {screen['benign']} benign requests. On the split "
         f"written apart from the rules and scored once, it decided {fresh['decisions_right']} of "
         f"{fresh['cases']} right and let {fresh['missed_violations']} of {fresh['violations']} violations "
         "through."),
        ("Containment",
         f"{contain['violations_past_the_screen']} violations passed the screen across all splits, and the scoped "
         f"tools, the verifier and the approval route contained {contain['contained']} of "
         f"{contain['violations_past_the_screen']}."),
        ("Verifier and output check",
         f"{check['clean_briefs_passed']} of {check['clean_briefs']} clean briefs pass, and the checks reject "
         f"{check['faults_rejected']} of {check['faults_seeded']} seeded faults. The "
         f"{check['faults_seeded'] - check['faults_rejected']} misses {missed_note}."),
        ("Monitor and approval gate",
         f"The monitor flagged {monitor['trace_faults_flagged']} of {monitor['trace_faults_seeded']} seeded trace "
         f"faults, and the gate refused {gate['invalid_decisions_refused']} of {gate['invalid_decisions']} invalid "
         "decisions."),
        ("Routing",
         f"{route['released_without_a_person']} of {route['requests']} requests were released without a person "
         f"and {route['waited_for_a_person']} of {route['requests']} waited for sign-off, "
         f"{route['escalation_rate_pct']}%. {route['held']} of {route['requests']} were held."),
        ("A model's paragraph",
         f"A stand-in model that copies the facts had {copies['first_draft_accepted']} of {copies['runs']} first "
         f"drafts accepted. One that invents a figure in every draft ended "
         f"{invents['ended_on_the_code_written_paragraph']} of {invents['runs']} runs on the code-written "
         f"paragraph, and {invents['same_route_as_the_code_written_run']} of {invents['runs']} kept the route of "
         "the code-written run."),
    ]


def limits(card: dict[str, Any]) -> list[str]:
    """What the scorecard cannot show, with the run counts read from the scorecard itself."""
    count, divide = card["model_alone"]["counting"], card["model_alone"]["dividing"]
    counting_runs = count["reading_the_rows"]["runs"] + count["reading_the_tool_summary"]["runs"]
    dividing_runs = divide["in_text"]["runs"] + divide["with_a_divide_tool"]["runs"]
    return [
        "All data is synthetic, and every test case was written for this project. The held-out splits were "
        "frozen before the code they test was tuned, and the request screen's last split was written from the "
        "policy alone and scored once.",
        "No compensation partner has used the advisor, so nothing here measures whether a brief helps a decision.",
        f"The two model baselines are {counting_runs} runs on one model and {dividing_runs} runs on another. "
        "They show that the failure exists, not how often it happens across models.",
        "A model's paragraph appears here only through stand-in models. `python3 -m src.evaluation.live_writer` "
        "runs a real one, and its saved runs sit next to this file.",
    ]


_NUMBER = r"(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)"
FIGURE_RE = re.compile(rf"\${_NUMBER}|{_NUMBER} of {_NUMBER}|[0-9]+(?:\.[0-9]+)?%")


def figures(text: str) -> set[str]:
    """Every dollar figure, "N of M" count and percentage a text states."""
    return set(FIGURE_RE.findall(text))


def quotable(card: dict[str, Any]) -> set[str]:
    """The figures a document may quote from this scorecard."""
    return figures(" ".join(text for _, text in headline(card)))


def render_markdown(card: dict[str, Any]) -> str:
    clock = card["timing"]
    lines = [
        "# Final evaluation scorecard",
        "",
        "`python3 -m src.evaluation.scorecard --write` wrote this file from `scorecard.json`. Every count comes "
        "from code run on the committed synthetic data. No model ran, apart from the two recorded baselines, "
        "whose answers sit in `experiments/rows_vs_summary` and `experiments/compa_ratio_drift`.",
        "",
        "| Area | Result |",
        "| :--- | :--- |",
    ]
    lines += [f"| {area} | {text} |" for area, text in headline(card)]
    lines += [
        "",
        "## Timing on the machine that wrote this file",
        "",
        f"A guarded run takes a median of {clock['guarded_median_ms']} ms against {clock['squad_alone_median_ms']} "
        f"ms for the squad alone, so the controls add {clock['controls_add_median_ms']} ms. A refusal takes "
        f"{clock['refusal_median_ms']} ms. Across all requests the median is {clock['all_requests_median_ms']} ms "
        f"and the slowest is {clock['all_requests_slowest_ms']} ms. These runs use the code-written summary, so "
        "they leave out the seconds a model takes to write.",
        "",
        "## What this scorecard does not show",
        "",
    ]
    lines += [f"- {limit}" for limit in limits(card)]
    return "\n".join(lines) + "\n"


def write(card: dict[str, Any], out_dir: Path = OUT_DIR) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / JSON_PATH.name).write_text(json.dumps(card, indent=1) + "\n", encoding="utf-8")
    (out_dir / MD_PATH.name).write_text(render_markdown(card), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    card = build()
    if "--json" in args:
        print(json.dumps(card, indent=1))
        return 0
    if "--write" in args:
        write(card)
        print(f"wrote {JSON_PATH.relative_to(PROJECT_ROOT)} and {MD_PATH.relative_to(PROJECT_ROOT)}")
        return 0
    for area, text in headline(card):
        print(f"{area}: {text}")
    if not JSON_PATH.exists():
        print(f"\nNo committed scorecard at {JSON_PATH.relative_to(PROJECT_ROOT)}. Run with --write to create it.")
        return 1
    changed = differences(stable(json.loads(JSON_PATH.read_text(encoding="utf-8"))), stable(card))
    if changed:
        print("\nThe committed scorecard no longer matches the code:")
        for line in changed:
            print(f"  {line}")
        return 1
    print("\nSCORECARD OK: every count matches the committed scorecard.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
