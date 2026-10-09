# CMU Agentic AI Capstone: Strategic Talent and Compensation Insight Advisor

This repository contains the coursework, checkpoints, synthetic data generators, and agent implementation for the CMU Executive Education Agentic AI Program. All data is synthetic.

## Status
All data is synthetic. Apex Cloud & AI Corp doesn't exist.
| Checkpoint | What works | Code |
| :--- | :--- | :--- |
| 1.1 Problem framing | Design and architecture diagram | `checkpoints/checkpoint_1_1.md` |
| 2.1 Tools and memory | In progress. SQL tools return counts and flags, never raw rows | `src/tools/` |
| 3.1 Policy retrieval | Not started | |
| 4.1 Tree-of-Thought planning | Not started | |
| 5.1 Multi-agent | Not started | |
| 6.1 Guardrails and approval | Not started | |
| 7.1 Evaluation | Not started | |


## Project Structure

- `checkpoints/` - Written submissions, diagrams, and deliverables for Checkpoints 1.1 through 7.1
- `data/synthetic/` - Scripts and generated SQLite/CSV datasets for the synthetic 2,000-employee org roster, multi-year cashflows, and reactive offer/counter-offer logs
- `docs/policies/` - Synthetic compensation policy documents and handoff playbooks indexed by ChromaDB for RAG
- `src/` - Agent source code, deterministic Pandas/SQLite tools, ChromaDB vector retrieval, and Gradio UI
- `tests/` - Evaluation scripts and guardrail checks
