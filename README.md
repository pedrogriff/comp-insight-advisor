# comp-insight-advisor

An AI research assistant for comp partners. It reads a synthetic company's pay, equity and offer data and drafts a retention brief. A comp partner reviews the brief and decides what goes to a VP. Models write the words. Code computes the money. People decide.

All data is synthetic. Apex Cloud & AI Corp doesn't exist.

This is my capstone for the 2026 *Agentic AI Program: Building Autonomous Systems for Real-World Applications*, an executive education program at Carnegie Mellon University's School of Computer Science. All seven build logs are on [LinkedIn](https://www.linkedin.com/in/pedrogriff/).

The current architecture diagram is in the final report, [checkpoint 7.1](checkpoints/checkpoint_7_1.md#system-architecture-diagram). Earlier versions are in [checkpoint 6.1](checkpoints/checkpoint_6_1.md#system-architecture-diagram), [checkpoint 5.1](checkpoints/checkpoint_5_1.md#system-architecture-diagram), [checkpoint 4.1](checkpoints/checkpoint_4_1.md#system-architecture-diagram), [checkpoint 3.1](checkpoints/checkpoint_3_1.md#system-architecture-diagram), [checkpoint 2.1](checkpoints/checkpoint_2_1.md#system-architecture-diagram) and [checkpoint 1.1](checkpoints/checkpoint_1_1.md#system-architecture-diagram).

## Review in five minutes

The final report is [checkpoints/checkpoint_7_1.md](checkpoints/checkpoint_7_1.md), with a PDF, the [presentation video](https://youtu.be/YprdRwfI1LU) and the presentation slides next to it.

**Read on GitHub, with nothing installed.**

1. [The final report](checkpoints/checkpoint_7_1.md), with the architecture diagram at the top.
2. [The scorecard](experiments/final_evaluation/scorecard.md), which states every result the report and the slides quote.
3. [Three requests and what came back](experiments/final_evaluation/sample_outputs.md): a costed brief with its approval record, a policy comparison and a refusal.
4. [The recorded model run](experiments/final_evaluation/live_writer_run1.json): 23 requests with `gemini-3.5-flash-lite` writing the summary, with every draft and the reason for the one rejection.

**Where each part of the [presentation video](https://youtu.be/YprdRwfI1LU) lives in the code.**

| In the video | Code |
| :--- | :--- |
| Org brief and joint plan | `src/agents/coordinator.py`, `src/planning/`, `src/tools/` |
| The model's summary and its fact check | `src/models/router.py`, `check_model_prose` in `src/guardrails/output_guard.py` |
| Approval gate and queue | `src/guardrails/approval.py`, `src/guardrails/pipeline.py` |
| Policy comparison | `src/retrieval/cross_lever.py`, `src/retrieval/policy_search.py` |
| Two refusals | `src/guardrails/input_guard.py` |
| Invented figure and the held run | `deterministic_verify_brief` in `src/agents/state.py`, `src/guardrails/monitor.py` |
| Console | `src/app.py` |
| Evaluation results | `src/evaluation/scorecard.py`, `experiments/final_evaluation/` |

**Run it.** Four commands show the system from a fresh clone. The first two need only Python 3.12 or newer.

```bash
python3 -m unittest discover -s tests                    # the tests, no network
python3 -m src.evaluation.scorecard                      # reruns every evaluation, ends with SCORECARD OK
pip install -r requirements.txt && python3 -m src.app    # the console at http://127.0.0.1:7860, six demo presets
python3 -m src.guardrails.pipeline run VP_CLOUD_AI       # one guarded brief on the command line
```

With a key in `.env`, a model writes the summary paragraph, and `python3 -m src.evaluation.live_writer --provider auto` shows what the checks did with each of its drafts. Without a key, code writes that paragraph, so all four commands run either way. [experiments/final_evaluation](experiments/final_evaluation/README.md) explains the scorecard, and [sample_outputs.md](experiments/final_evaluation/sample_outputs.md) shows three requests with what came back.

## Architecture

One request passes a screen, five nodes and a set of checks, and ends in one of three ways. The diagram and the full walk-through are in [the final report](checkpoints/checkpoint_7_1.md#system-architecture-diagram).

1. **G1, the request screen.** It checks the playbook's hash and refuses prompt injection, questions about one person's pay, protected attributes, write orders and orgs outside the partner's scope, before any tool or model runs.
2. **The squad.** Five nodes run as a LangGraph `StateGraph` and pass typed state: a supervisor, a proactive strategist and a reactive analyst in parallel, an executive synthesizer and a governance reviewer. Each node holds at most 3 of the 12 tools, and the tools open the database read-only.
3. **The model.** One call writes the summary paragraph, because wording is the one step with no exact answer. Code holds each draft to the facts the model was given, and after two rejected tries the brief keeps the code-written paragraph. With no API key, code writes the paragraph.
4. **G4 and the risk router.** The output check and the runtime monitor read the finished run. A cited policy answer or a brief with no spend is released, a costed brief waits at the approval gate, and any flag holds the run for a person.

## Status

All seven checkpoints are complete.

| Checkpoint | What works | Code |
| :--- | :--- | :--- |
| 1.1 Problem framing | Design and architecture diagram | `checkpoints/checkpoint_1_1.md` |
| 2.1 Reasoning, memory and tools | Design written, graded, and corrected on Oct 22. SQL tools return counts, averages and totals instead of the raw roster. The evidence check, partner memory and the new driver-fit check pass their tests | `checkpoints/checkpoint_2_1.md`, `src/tools/`, `src/memory/` |
| 3.1 Policy retrieval | Design written and graded. The code cuts the playbook into 38 rules tagged by lever and population, and each lever in a brief gets its own filtered search. A check confirms that the limits the code applies appear in the retrieved clauses. On 24 test questions, keyword search finds the right clause for 11, dense search on `nomic-embed-text` for 24 and hybrid search for 23. Keyword search returns nothing for all 4 questions the playbook doesn't cover, and the embedding modes return nothing for 3. After grading, a router splits a question that spans levers, such as "Compare the equity caps for new hires versus current staff", into one filtered query per side. On 7 held-out comparisons, keyword search answers 5 of 11 sides that way against 0 with one query, and no clause lands under the wrong population | `checkpoints/checkpoint_3_1.md`, `src/retrieval/`, `docs/policies/`, `experiments/policy_retrieval/` |
| 4.1 Tree-of-Thought planning | Design written and graded. A beam search, width 3 and depth up to 4, grows lever plans one decision at a time. Code checks every plan for eligibility, repeats, joint pricing, budget and sign-offs, and the planner returns three distinct options. On the three cohorts that pass the evidence check, its best plan inside the budget addresses 3 of 4, 7 of 7 and 4 of 5 departures, against 1 of 4, 6 of 7 and 3 of 5 for the template options. After grading, `beam_validation.py` checks width 3 against all 32 cohort plans and 105 budget thresholds, matching all 9 options and all 15 Pareto plans while cutting model calls by 67.7% | `checkpoints/checkpoint_4_1.md`, `src/planning/` |
| 5.1 Multi-agent | Design written and submitted. Five specialists run in a state graph with at most 3 tools per node, parallel internal and market checks merged with `operator.add`, shared-budget composition in `plan_org_options`, and an independent Python verifier capped at 2 revisions. On `VP_CLOUD_AI`, one generalist agent prices standalone cohort plans at $3,246,000, $1,096,000 over the $2,150,000 budget, while the squad composes a $1,995,600 joint plan covering 7 of 11 departures and 16 of 16 declined offers | `checkpoints/checkpoint_5_1.md`, `src/agents/` |
| 6.1 Guardrails and approval | Design written. The squad now compiles as a LangGraph `StateGraph` (`Send()`, `SqliteSaver`, `interrupt()`, `Command(resume=...)`) with a standard-library fallback. `GuardedAdvisor` screens requests (`0 of 50` false refusals across 4 splits, `40 of 48` on untouched `held_out_2`, `10 of 10` leaked violations contained downstream), opens roster SQLite read-only (`?mode=ro`), checks playbook SHA-256 integrity, rejects `158 of 163` seeded brief faults (`155 of 160` at submission, before the final evaluation added 3 policy-answer faults), flags `7 of 7` trace faults, routes `18 of 23` runs to `AUTO_RELEASE` and `5 of 23` (`21.7%`) to durable SQLite sign-off, logs a SHA-256 hash chain, and serves a three-tab Gradio console (`src/app.py`) | `checkpoints/checkpoint_6_1.md`, `src/guardrails/`, `src/agents/graph.py`, `src/models/router.py`, `src/app.py` |
| 7.1 Final report and evaluation | Final report written, with eight presentation slides. One command reruns every evaluation and compares the counts with the committed scorecard, and a test holds every dollar figure, percentage and N-of-M count in the report and on the slides to that file. The final evaluation found that the reviewer skipped the numbers in a policy answer's prose, which goes out without a person. The reviewer now checks them. A model's summary paragraph is also held to the facts it was given: a draft that adds a number or a forbidden claim gets one retry, and after that the brief keeps the code-written paragraph. A stand-in model that invents a figure in every draft ended `23 of 23` runs on the code-written paragraph. In the recorded run with `gemini-3.5-flash-lite`, `22 of 23` runs ended on the model's first draft, the fact check rejected 1 draft that promised a guaranteed outcome, and the redraft passed. The last two grader comments are answered too. The roster scan had been passing rows with employee IDs into shared state, so tools now hand over counts only, the monitor holds any run whose state names an employee (`8 of 8` seeded trace faults flagged), and `0 of 23` final states do. The scorecard also counts what sent the 5 waiting briefs to a person | `checkpoints/checkpoint_7_1.md`, `src/evaluation/`, `experiments/final_evaluation/`, `scripts/generate_final_slides_pdf.py` |

## Quick start (Gradio UI and CLI)

The tools, guardrails, standard-library squad engine, and offline unit tests run on Python 3.12 or newer (3.10+ compatible) with zero third-party packages. Installing `requirements.txt` enables the Gradio partner console (`src/app.py`) and the compiled LangGraph `StateGraph` + `SqliteSaver` engine (`src/agents/graph.py`).

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate, and python in place of python3
pip install -r requirements.txt

# To have a model write the summary, copy .env.example to .env and paste OPENROUTER_API_KEY,
# GEMINI_API_KEY or OPENAI_API_KEY (or set OLLAMA_ENABLED=true with a local Ollama server).
# Without any key, code writes the summary and everything else runs the same.
cp .env.example .env

# Launch the three-tab Gradio console at http://127.0.0.1:7860
python3 -m src.app

# Run the full test suite and the final scorecard
python3 -m unittest discover -s tests
python3 -m src.evaluation.scorecard

# With a key in .env: check that the model answers and see what the checks do with its drafts
python3 -m src.evaluation.live_writer --provider auto
```

## What's in the repo today

- `data/synthetic/generate_synthetic_data.py` builds the dataset from a fixed seed. It writes 2,000 employees across 4 VP orgs, 350 offer and counter-offer events and 4 department budgets, as three CSV files and one SQLite database.
- `src/tools/deterministic_analytics.py` holds the read-only SQLite tools (`?mode=ro`) the specialists call:
  - `analyze_org_cliff_and_equity_health` counts employees whose cash flow drops by 15 percent or more from 2026 to 2027, with peer percentiles and counts of governance flags by job family. No tool returns a row about one employee.
  - `analyze_reactive_offers_and_counters` summarizes offer acceptance, counter-offers and competitor premiums.
  - `simulate_proactive_retention_scenarios` prices three retention plans with a 4-tier sizing rubric and checks each one against the org's remaining budget. Tier 0 comes first, so nobody rated 1 or 2 gets a proactive grant.
- `src/tools/evidence_check.py` holds `assess_retention_evidence`, which runs after the roster scan flags a job family. It treats roster counts as a census, puts a 95 percent interval on every rate or average from the offers log, labels the pattern, such as a cliff backed by market pressure or a cliff in a calm market, and rates the evidence strong, moderate or weak. Only a cliff backed by conclusive market pressure lets a brief cost retention spend.
- `src/memory/partner_memory.py` keeps partner feedback across sessions in SQLite. It proposes a standing preference after the same edit appears in 3 separate sessions, applies it only after the partner confirms, sends it back after 180 days or a contradicting edit, and raises `PolicyLockedError` for any edit that would switch off a governance check.
- `src/tools/intervention_fit.py` holds `assess_intervention_fit`, which runs after the evidence check. It counts the reasons people gave for leaving after a counter-offer apart from the reasons candidates gave for declining, matches each reason to the lever that addresses it, and costs the brief's three options, including off-cycle base adjustments and level reviews priced as promotions. When retention grants address fewer than half of the departures, it flags a mismatch and Option C adds the other levers. An employee costed for both a base lift and a promotion counts once, because the promotion already moves base past the lift ceiling, and `joint_pricing` holds that rule for the Tree-of-Thought planner too.
- `data/synthetic/generate_interview_notes.py` writes 261 synthetic interview notes: one exit note per employee who left after a counter-offer, one stay note per accepted counter-offer, and a proactive stay interview with every cliff-facing employee in the three hotspot job families. It also writes 10 retrieval cases labeled from note metadata.
- `src/tools/interview_search.py` searches those notes with BM25, metadata filters, query expansion from a small glossary, sub-queries for mixed questions and maximal marginal relevance. `python3 -m src.tools.interview_search --evaluate` prints precision, recall and diversity for each case.
- `src/retrieval/` is the retrieval layer for checkpoint 3.1:
  - `embeddings.py` turns text into vectors through Ollama or an OpenAI-compatible endpoint, such as Gemini's. A built-in hashing embedder needs no model and serves the tests, and a saved-scores embedder replays a recorded run without the model.
  - `hybrid_index.py` ranks documents with BM25 and with embeddings, merges the two rankings by reciprocal rank fusion and filters on metadata first. It returns nothing when no document matches at least half of the query's terms and none clears the embedder's similarity threshold. It can keep vectors in a SQLite file that rebuilds when the corpus or the embedding model changes.
  - `policy_search.py` cuts the playbook into 38 rules, one per bullet, numbered item or paragraph, and tags each with the levers it governs and the population it covers. The agent's queries filter on the lever, so a question about a raise never gets the new-hire offer rule. `check_limits` confirms that each limit the code applies, such as the 0.95 lift ceiling, appears in a retrieved clause, and `verify_rule` checks a drafted rule against the clause it cites. `--evaluate` scores keyword, dense and hybrid search on 18 tuning questions and 10 held-out ones from `data/synthetic/policy_retrieval_cases.json`.
  - `grounded_options.py` runs after the driver-fit check. It retrieves the clauses behind each lever and each checklist item, checks the code's limits against them, and looks up every exit note for the cohort. `--compare` prints the same brief inputs with and without retrieval.
  - `cross_lever.py` answers a partner's question that spans levers or populations. It names the sides from the question's words, rewrites one query per side without the population words, runs each inside a strict population and lever filter, and hands the writer one labeled group per side. A side the playbook doesn't cover stays empty, and `verify_comparison` rejects a claim whose clause came from another side. `--evaluate` compares it with one query on 5 tuning and 7 held-out comparisons from `data/synthetic/cross_lever_cases.json`.
- `src/planning/tot_planner.py` is the Tree-of-Thought planner for checkpoint 4.1. Each thought adds one lever to a plan, the tools price the plan, and code prunes plans that nobody is eligible for, that add nothing, that repeat another plan or that another plan beats on coverage, cost and sign-offs. A base lift and a promotion for the same employee count once. A beam of 3 keeps the best plans at each depth, and the decision maker returns the most coverage inside the budget, the most coverage at any cost and the cheapest plan that answers at least half of the departures. `--compare` sets it against the template options, a chain that starts with grants, a chain that scores each step, and all 32 plans.
- `src/planning/beam_validation.py` tests beam widths 1 to 4 against exhaustive 32-plan search across 105 budget thresholds per cohort, and compares a flat multi-cohort beam with `plan_org_options`, which composes per-cohort Pareto fronts across 1,024 and 32,768 joint plans.
- `src/agents/` is the five-agent squad for checkpoints 5.1 and 6.1:
  - `state.py` defines `SquadState`, `Finding`, `ExecutiveBrief`, `ThreadCheckpointer`, `ScopedToolExecutor` with per-role tool allowlists, session-set `allowed_orgs`, and a duplicate-call guard, and `deterministic_verify_brief` with per-option figure triple checks.
  - `coordinator.py` runs `supervisor`, parallel `proactive_strategist` and `reactive_analyst` merged with `operator.add`, `executive_synthesizer` with `plan_org_options`, and `governance_reviewer` with a 2-revision cap before human hold. `--compare` benchmarks one generalist agent with all 12 tools against the squad on `VP_CLOUD_AI`.
  - `serialization.py`, `checkpoint_store.py` and `graph.py` encode `SquadState` losslessly as JSON, persist step snapshots to SQLite (`SqliteThreadCheckpointer`), and compile the same squad as a LangGraph `StateGraph` (`LangGraphSquad`) with `Send()`, `SqliteSaver`, `interrupt()`, and `Command(resume=...)`.
- `src/guardrails/` wraps the squad for checkpoint 6.1:
  - `integrity.py` checks `docs/policies/compensation_governance_playbook.md` against its SHA-256 manifest (`docs/policies/playbook_manifest.json`).
  - `input_guard.py` screens requests before any tool or model runs across 8 ordered rules (`empty`, `oversized`, `injection`, `protected_attribute`, `individual_pay`, `write_action`, `out_of_scope`, `unknown_scope`, and session `cross_org`).
  - `output_guard.py` and `monitor.py` verify propositions beyond the figure checker (`EMP_` ID leaks, guaranteed outcomes, decision claims) and audit trajectory transitions and tool/message budgets. The monitor also holds any run whose shared state names an employee. `check_model_prose` holds a paragraph a model wrote to the code-written facts it was given, so the model can reword a sentence but can't add a number.
  - `approval.py`, `audit.py` and `pipeline.py` route runs across `AUTO_RELEASE`, `PARTNER_APPROVAL`, `EXECUTIVE_SIGN_OFF`, and `HOLD`, store waiting briefs in SQLite (`ApprovalStore`), and append SHA-256 hash-chained records to `AuditLog`. `python3 -m src.guardrails.pipeline triggers` counts which signals sent stored briefs to a person, most frequent first. `evaluate.py` runs the full guardrail benchmark over `data/synthetic/guardrail_cases.json` (136 cases across 4 splits).
- `src/models/router.py` maps fast and reasoning roles to models on OpenRouter, the Google Gemini API, the OpenAI API or a local Ollama server. One step calls a model today, the summary paragraph. Each draft is checked against the facts, a rejected draft gets one retry, and after that the brief keeps the code-written paragraph. `ADVISOR_REASONING_MODEL` in `.env` swaps the model without a code change. With no key, code writes the paragraph. When a call fails, the call log keeps the provider's reason, and the brief keeps the code-written paragraph.
- `src/evaluation/` is the final evaluation for checkpoint 7.1:
  - `scorecard.py` reruns every offline evaluation, from the two recorded model baselines to the guardrails, and compares the counts with `experiments/final_evaluation/scorecard.json`. It reads the recorded model run and checks its saved drafts again against today's checks. `--write` rewrites that file and `scorecard.md`.
  - `live_writer.py` runs the 23 requests with a real model writing the summary, next to a code-written run of each, and records every draft and why any was rejected. `--save` keeps the run and `--replay` checks a saved run against today's checks with no model.
- `src/app.py` serves the three-tab Gradio partner console: quick-load demo presets, request & RBAC scope controls, expandable cited playbook clauses, bounded human approval decision card, durable SQLite pending/held queue, collapsible step trace & `Finding` inspector, and two-step preview-and-commit `PartnerMemory` controls. The status card names what wrote each summary, a model or code, and the trace lists every draft with the reason for any rejection.
- `tests/` runs 238 checks (`232` run offline with zero packages; `6` live `LangGraphEngineTests` run when `langgraph` is installed): 5 for the SQL tools, 13 for the evidence check, 13 for partner memory, 18 for the driver-fit check, 2 for joint pricing, 15 for interview search, 9 for embeddings and the hybrid index, 17 for policy retrieval and grounded options, 18 for the cross-lever router, 12 for the Tree-of-Thought planner, 11 for beam validation and org composition, 7 for multi-agent coordination, 4 for state serialization, 10 for the LangGraph node wrappers and `StateGraph` engine, 26 for guardrails, approval gates, the shared-state check and hash-chained audit logs, 6 for the model router and Gradio app controller, 27 for the final scorecard, the model fact check, the live writer check and the recorded run, 12 for the final report, its link and the slides, and 13 for the compa-ratio drift experiment.
- `docs/policies/compensation_governance_playbook.md` is the synthetic policy the agent retrieves from. Section 6 maps each loss driver to the lever that addresses it.
- `checkpoints/` holds the written submissions. `scripts/generate_checkpoint_pdf.py` and `scripts/generate_checkpoint_2_1_pdf.py` through `scripts/generate_checkpoint_6_1_pdf.py` render the PDF copies of checkpoints 1.1 through 6.1 with Playwright. `scripts/generate_checkpoint_7_1_pdf.py` renders the final report and the one-page document with the video link, `scripts/set_submission_links.py` puts the video link into both, and `scripts/generate_final_slides_pdf.py` renders the eight presentation slides.

## Command-line walkthrough

Run these from the repo root:

```bash
python3 data/synthetic/generate_synthetic_data.py
python3 -c "import json; from src.tools.deterministic_analytics import analyze_org_cliff_and_equity_health as f; print(json.dumps(f('VP_CLOUD_AI'), indent=2))"
python3 -c "import json; from src.tools.evidence_check import assess_retention_evidence as f; print(json.dumps(f('VP_CLOUD_AI', 'RESEARCH_SCI'), indent=2))"
python3 -c "import json; from src.tools.intervention_fit import assess_intervention_fit as f; print(json.dumps(f('VP_CLOUD_AI', 'RESEARCH_SCI'), indent=2))"
python3 -m src.tools.interview_search --evaluate
python3 -m src.retrieval.policy_search --evaluate
python3 -m src.retrieval.policy_search --evaluate --embedder saved:experiments/policy_retrieval/nomic-embed-text.json
python3 -m src.retrieval.grounded_options VP_CLOUD_AI RESEARCH_SCI --compare
python3 -m src.retrieval.cross_lever "Compare the equity caps for new hires versus current staff"
python3 -m src.retrieval.cross_lever --evaluate
python3 -m src.planning.tot_planner VP_CLOUD_AI RESEARCH_SCI
python3 -m src.planning.tot_planner --compare
python3 -m src.planning.beam_validation
python3 -m src.planning.beam_validation --org
python3 -m src.agents.coordinator VP_CLOUD_AI
python3 -m src.agents.coordinator --compare
python3 -m src.guardrails.pipeline run VP_CLOUD_AI
python3 -m src.guardrails.pipeline ask "How do equity caps differ for new hires versus current staff?"
python3 -m src.guardrails.pipeline triggers
python3 -m src.guardrails.evaluate
python3 -m src.evaluation.scorecard
python3 -m src.evaluation.live_writer --provider auto
python3 -m src.evaluation.live_writer --replay experiments/final_evaluation/live_writer_run1.json
python3 -m src.models.router --status
python3 -m src.app --check
python3 scripts/set_submission_links.py --check
python3 -m unittest discover -s tests
```

The repo includes the database and the interview notes, so every command after the first also works without it.

Retrieval runs on keyword search alone unless you name an embedding model. With [Ollama](https://ollama.com) running and `ollama pull nomic-embed-text` done, add `--embedder ollama:nomic-embed-text` to either retrieval command. The evaluation then adds dense and hybrid rows and prints the best similarity score for each question, which sets the threshold below which the agent says no clause covers a question. `--index vector_index/policy.sqlite` keeps the vectors between runs, and git ignores that folder. `--save experiments/policy_retrieval/nomic-embed-text-test.json` writes the model's score for every test question and agent query against every clause without overwriting the committed Oct 24 baseline, and `--embedder saved:experiments/policy_retrieval/nomic-embed-text.json` replays the committed Oct 24 run without the model. [experiments/policy_retrieval](experiments/policy_retrieval/README.md) explains the saved files, including `nomic-embed-text-router.json` from Oct 30.

The generator is deterministic. A rerun writes the same three CSV files byte for byte and the same rows into the database. Git still shows the `.db` file as changed, because SQLite stores those rows on different pages. `git checkout data/synthetic/comp_insight_advisor.db` restores the committed copy.

## Build log

| # | Date | Post | Topic |
| :--- | :--- | :--- | :--- |
| 1 | Oct 13 | [Build log 1/7](https://www.linkedin.com/feed/update/urn:li:activity:7515786546697117696/) | An agent that isn't allowed to do math |
| 2 | Oct 20 | [Build log 2/7](https://www.linkedin.com/feed/update/urn:li:activity:7518326192945430531/) | 500 rows vs. 5 numbers |
| 3 | Oct 27 | [Build log 3/7](https://www.linkedin.com/posts/pedrogriff_agenticai-rag-compensation-share-7520915421089263616-xyO_) | The right rule for the wrong people |
| 4 | Nov 3 | [Build log 4/7](https://www.linkedin.com/feed/update/urn:li:activity:7523451374332858368/) | Two of my three plans were the same plan |
| 5 | Nov 10 | [Build log 5/7](https://www.linkedin.com/feed/update/urn:li:activity:7525990176800616448/) | One agent vs. three, measured |
| 6 | Nov 17 | [Build log 6/7](https://www.linkedin.com/feed/update/urn:li:activity:7528650394504249344/) | 155 of 160 planted faults caught |
| 7 | Nov 24 | [Build log 7/7](https://www.linkedin.com/feed/update/urn:li:activity:7531228842783408128/) | Demo and scorecard |

## License

MIT
