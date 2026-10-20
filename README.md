# comp-insight-advisor

An AI research assistant for comp partners. It reads a synthetic company's pay, equity and offer data and drafts a retention brief. A comp partner reviews the brief and decides what goes to a VP. Models write the words. Code computes the money. People decide.

All data is synthetic. Apex Cloud & AI Corp doesn't exist.

This is my capstone for the 2026 *Agentic AI Program: Building Autonomous Systems for Real-World Applications*, an executive education program at Carnegie Mellon University's School of Computer Science. I post a build log every Tuesday on [LinkedIn](https://www.linkedin.com/in/pedrogriff/).

The current architecture diagram is in [checkpoint 2.1](checkpoints/checkpoint_2_1.md#system-architecture-diagram). The first version is in [checkpoint 1.1](checkpoints/checkpoint_1_1.md#system-architecture-diagram).

## Status

Updated every Tuesday.

| Checkpoint | What works | Code |
| :--- | :--- | :--- |
| 1.1 Problem framing | Design and architecture diagram | `checkpoints/checkpoint_1_1.md` |
| 2.1 Reasoning, memory and tools | Design written. SQL tools return counts, averages and up to 15 flagged rows instead of the raw roster. The evidence check and partner memory pass their tests. The ReAct loop is next | `checkpoints/checkpoint_2_1.md`, `src/tools/`, `src/memory/` |
| 3.1 Policy retrieval | Not started | |
| 4.1 Tree-of-Thought planning | Not started | |
| 5.1 Multi-agent | Not started | |
| 6.1 Guardrails and approval | Not started | |
| 7.1 Evaluation | Not started | |

## What's in the repo today

- `data/synthetic/generate_synthetic_data.py` builds the dataset from a fixed seed. It writes 2,000 employees across 4 VP orgs, 350 offer and counter-offer events and 4 department budgets, as three CSV files and one SQLite database.
- `src/tools/deterministic_analytics.py` holds the tools the agent will call:
  - `analyze_org_cliff_and_equity_health` counts employees whose cash flow drops by 15 percent or more from 2026 to 2027, with peer percentiles and governance flags.
  - `analyze_reactive_offers_and_counters` summarizes offer acceptance, counter-offers and competitor premiums.
  - `simulate_proactive_retention_scenarios` prices three retention plans with a 4-tier sizing rubric and checks each one against the org's remaining budget.
- `src/tools/evidence_check.py` holds `assess_retention_evidence`, which runs after the roster scan flags a job family. It treats roster counts as a census, puts a 95 percent interval on every rate or average from the offers log, labels the pattern, such as a cliff backed by market pressure or a cliff in a calm market, and rates the evidence strong, moderate or weak. Only a cliff backed by conclusive market pressure lets a brief cost retention spend.
- `src/memory/partner_memory.py` keeps partner feedback across sessions in SQLite. It proposes a standing preference after the same edit appears in 3 separate sessions, applies it only after the partner confirms, sends it back after 180 days or a contradicting edit, and raises `PolicyLockedError` for any edit that would switch off a governance check.
- `tests/` runs 30 checks: 4 for the SQL tools, 13 for the evidence check and 13 for partner memory.
- `docs/policies/compensation_governance_playbook.md` is the synthetic policy the agent will retrieve from in checkpoint 3.1.
- `checkpoints/` holds the written submissions. `scripts/generate_checkpoint_pdf.py` and `scripts/generate_checkpoint_2_1_pdf.py` render the PDF copies of checkpoints 1.1 and 2.1 with Playwright.

## Run it

The generator, the tools and the tests need Python 3.10 or newer and the standard library only. Later checkpoints add the packages in `requirements.txt`.

Run these from the repo root:

```bash
python3 data/synthetic/generate_synthetic_data.py
python3 -c "import json; from src.tools.deterministic_analytics import analyze_org_cliff_and_equity_health as f; print(json.dumps(f('VP_CLOUD_AI'), indent=2))"
python3 -c "import json; from src.tools.evidence_check import assess_retention_evidence as f; print(json.dumps(f('VP_CLOUD_AI', 'RESEARCH_SCI'), indent=2))"
python3 -m unittest discover tests
```

The database is committed, so the last three commands also work without the first.

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
