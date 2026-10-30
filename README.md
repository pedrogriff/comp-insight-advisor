# comp-insight-advisor

An AI research assistant for comp partners. It reads a synthetic company's pay, equity and offer data and drafts a retention brief. A comp partner reviews the brief and decides what goes to a VP. Models write the words. Code computes the money. People decide.

All data is synthetic. Apex Cloud & AI Corp doesn't exist.

This is my capstone for the 2026 *Agentic AI Program: Building Autonomous Systems for Real-World Applications*, an executive education program at Carnegie Mellon University's School of Computer Science. I post a build log every Tuesday on [LinkedIn](https://www.linkedin.com/in/pedrogriff/).

The current architecture diagram is in [checkpoint 4.1](checkpoints/checkpoint_4_1.md#system-architecture-diagram). Earlier versions are in [checkpoint 3.1](checkpoints/checkpoint_3_1.md#system-architecture-diagram), [checkpoint 2.1](checkpoints/checkpoint_2_1.md#system-architecture-diagram) and [checkpoint 1.1](checkpoints/checkpoint_1_1.md#system-architecture-diagram).

## Status

Updated every Tuesday.

| Checkpoint | What works | Code |
| :--- | :--- | :--- |
| 1.1 Problem framing | Design and architecture diagram | `checkpoints/checkpoint_1_1.md` |
| 2.1 Reasoning, memory and tools | Design written, graded, and corrected on Oct 22. SQL tools return counts, averages and up to 15 flagged rows instead of the raw roster. The evidence check, partner memory and the new driver-fit check pass their tests. The ReAct loop is next | `checkpoints/checkpoint_2_1.md`, `src/tools/`, `src/memory/` |
| 3.1 Policy retrieval | Design written and graded. The code cuts the playbook into 38 rules tagged by lever and population, and each lever in a brief gets its own filtered search. A check confirms that the limits the code applies appear in the retrieved clauses. On 24 test questions, keyword search finds the right clause for 11, dense search on `nomic-embed-text` for 24 and hybrid search for 23. Keyword search returns nothing for all 4 questions the playbook doesn't cover, and the embedding modes return nothing for 3. After grading, a router splits a question that spans levers, such as "Compare the equity caps for new hires versus current staff", into one filtered query per side. On 7 held-out comparisons, keyword search answers 5 of 11 sides that way against 0 with one query, and no clause lands under the wrong population | `checkpoints/checkpoint_3_1.md`, `src/retrieval/`, `docs/policies/`, `experiments/policy_retrieval/` |
| 4.1 Tree-of-Thought planning | Design written. A beam search, width 3 and depth up to 4, grows lever plans one decision at a time. Code checks every plan for eligibility, repeats, joint pricing, budget and sign-offs, and the planner returns three distinct options. On the three cohorts that pass the evidence check, its best plan inside the budget addresses 3 of 4, 7 of 7 and 4 of 5 departures, against 1 of 4, 6 of 7 and 3 of 5 for the template options | `checkpoints/checkpoint_4_1.md`, `src/planning/` |
| 5.1 Multi-agent | Not started | |
| 6.1 Guardrails and approval | Not started | |
| 7.1 Evaluation | Not started | |

## What's in the repo today

- `data/synthetic/generate_synthetic_data.py` builds the dataset from a fixed seed. It writes 2,000 employees across 4 VP orgs, 350 offer and counter-offer events and 4 department budgets, as three CSV files and one SQLite database.
- `src/tools/deterministic_analytics.py` holds the tools the agent will call:
  - `analyze_org_cliff_and_equity_health` counts employees whose cash flow drops by 15 percent or more from 2026 to 2027, with peer percentiles and governance flags.
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
- `tests/` runs 135 checks: 5 for the SQL tools, 13 for the evidence check, 13 for partner memory, 18 for the driver-fit check, 2 for joint pricing, 15 for interview search, 9 for embeddings and the hybrid index, 17 for policy retrieval and grounded options, 18 for the cross-lever router, 12 for the Tree-of-Thought planner, and 13 for the compa-ratio drift experiment. Four of the policy retrieval checks and two of the router checks replay saved `nomic-embed-text` scores, so none of the 135 needs a model or a network.
- `docs/policies/compensation_governance_playbook.md` is the synthetic policy the agent retrieves from. Section 6 maps each loss driver to the lever that addresses it.
- `checkpoints/` holds the written submissions. `scripts/generate_checkpoint_pdf.py`, `scripts/generate_checkpoint_2_1_pdf.py`, `scripts/generate_checkpoint_3_1_pdf.py` and `scripts/generate_checkpoint_4_1_pdf.py` render the PDF copies of checkpoints 1.1, 2.1, 3.1 and 4.1 with Playwright.

## Run it

The generator, the tools and the tests need Python 3.10 or newer and the standard library only. Later checkpoints add the packages in `requirements.txt`.

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
python3 -m unittest discover tests
```

The repo includes the database and the interview notes, so every command after the first also works without it.

Retrieval runs on keyword search alone unless you name an embedding model. With [Ollama](https://ollama.com) running and `ollama pull nomic-embed-text` done, add `--embedder ollama:nomic-embed-text` to either retrieval command. The evaluation then adds dense and hybrid rows and prints the best similarity score for each question, which sets the threshold below which the agent says no clause covers a question. `--index vector_index/policy.sqlite` keeps the vectors between runs, and git ignores that folder. `--save experiments/policy_retrieval/nomic-embed-text.json` on the evaluation writes the model's score for every test question and agent query against every clause, and `--embedder saved:experiments/policy_retrieval/nomic-embed-text.json` then replays that run without the model. The repo includes the scores from Oct 24, and [experiments/policy_retrieval](experiments/policy_retrieval/README.md) explains them. Those scores predate the cross-lever router. `nomic-embed-text-router.json`, saved on Oct 30, adds the router's queries, and `cross_lever --evaluate --embedder saved:experiments/policy_retrieval/nomic-embed-text-router.json` replays the router in hybrid mode.

The generator is deterministic. A rerun writes the same three CSV files byte for byte and the same rows into the database. Git still shows the `.db` file as changed, because SQLite stores those rows on different pages. `git checkout data/synthetic/comp_insight_advisor.db` restores the committed copy.

## Build log

| # | Date | Post | Topic |
| :--- | :--- | :--- | :--- |
| 1 | Oct 13 | [Build log 1/7](https://www.linkedin.com/feed/update/urn:li:activity:7515786546697117696/) | An agent that isn't allowed to do math |
| 2 | Oct 20 | [Build log 2/7](https://www.linkedin.com/feed/update/urn:li:activity:7518326192945430531/) | 500 rows vs. 5 numbers |
| 3 | Oct 27 | | Retrieval found the old policy |
| 4 | Nov 3 | | Two of my three plans were the same plan |
| 5 | Nov 10 | | One agent vs. three, measured |
| 6 | Nov 17 | | The checker caught an invented number |
| 7 | Nov 24 | | Demo and scorecard |

## License

MIT
