# Policy retrieval scores

Does an embedding model find the playbook rule that answers a comp partner's question when keyword search can't, and does it return nothing when no rule answers? This folder holds the scores behind the dense and hybrid rows in [checkpoint 3.1](../../checkpoints/checkpoint_3_1.md).

All data is synthetic. Apex Cloud & AI Corp doesn't exist.

## What's here

- `nomic-embed-text.json` holds the similarity score that `nomic-embed-text`, run locally through Ollama on Oct 24, 2026, gave each of 48 queries against each of the playbook's 38 rule chunks. The queries are the 28 test questions in `data/synthetic/policy_retrieval_cases.json`, the 3 demo questions in `src/retrieval/policy_search.py` and the 17 queries the agent sends for the three cohorts in `COHORTS`.
- `nomic-embed-text-router.json` holds the scores the same model gave on Oct 30, 2026, on the personal machine, to 108 queries against the same 38 chunks: the queries above plus every query the cross-lever router and its baselines send for the 28 test questions and the 12 comparison questions in `data/synthetic/cross_lever_cases.json`.
- Each file also stores the chunk IDs and a hash of the chunk texts. If the playbook changes, the replay stops with an error, and `tests/test_policy_retrieval.py` fails until someone saves the scores again with the model.

## Run it

From the repo root, with Ollama running and `ollama pull nomic-embed-text` done, this command scores the questions and saves the file:

```bash
python3 -m src.retrieval.policy_search --evaluate --embedder ollama:nomic-embed-text --save experiments/policy_retrieval/nomic-embed-text.json
```

These replay the saved scores without Ollama:

```bash
python3 -m src.retrieval.policy_search --evaluate --embedder saved:experiments/policy_retrieval/nomic-embed-text.json
python3 -m src.retrieval.grounded_options VP_CLOUD_AI RESEARCH_SCI --compare --embedder saved:experiments/policy_retrieval/nomic-embed-text.json
```

## Results

A replay uses the 0.60 threshold in `MIN_SIMILARITY` in `src/retrieval/embeddings.py`, not the 0.55 that the file recorded at save time. The 0.60 comes from the 16 dev questions alone. Every answerable one had a clause scoring at least 0.607, and neither unanswerable one had a clause above 0.584. The 10 held-out questions ran once, at 0.60.

| Search | Dev: right clause in top 3 | Held-out: right clause in top 3 | Unanswerable: nothing returned | Context words per question |
| :--- | ---: | ---: | ---: | ---: |
| Keyword, BM25 | 8 of 16 | 3 of 8 | 4 of 4 | 47 |
| Dense | 16 of 16 | 8 of 8 | 3 of 4 | 113 |
| Hybrid | 16 of 16 | 7 of 8 | 3 of 4 | 122 |

- Dense search finds the right clause for all 24 answerable questions, including the 13 that keyword search misses.
- Hybrid search misses H3, "Who signs off on the largest retention awards?", because keyword matches on "sign-off" push the Tier 3 rule out of the top 3.
- Both embedding modes answer H10, "How much is the annual bonus for sales staff?", with `6.3:cost-candidate` at 0.666. That clause mentions the bonus target for a level review.
- For "Is there a compa-ratio cap for equity?", dense search scores `6.2:floor` at 0.700 and the new-hire clause `2.1:thresholds` at 0.698, and hybrid search ranks the new-hire clause first. The lever filter keeps that clause out of every retention query.
- With hybrid search, the three cohorts get the same checklist clauses as with keyword search, and no checklist item goes unsupported.

`NomicRunTest` in `tests/test_policy_retrieval.py` replays this file and checks these results.

## The cross-lever router

`nomic-embed-text-router.json` replays the router without Ollama, in hybrid mode:

```bash
python3 -m src.retrieval.cross_lever --evaluate --embedder saved:experiments/policy_retrieval/nomic-embed-text-router.json
```

| Search | Dev sides answered | Dev questions fully right | Held-out sides answered | Held-out empty sides kept empty | Held-out questions fully right |
| :--- | ---: | ---: | ---: | ---: | ---: |
| Keyword, one query, no filter | 3 of 9 | 1 of 5 | 0 of 11 | 3 of 3 | 1 of 7 |
| Keyword, one query per side | 8 of 9 | 4 of 5 | 5 of 11 | 3 of 3 | 3 of 7 |
| Hybrid, one query, no filter | 5 of 9 | 0 of 5 | 5 of 11 | 2 of 3 | 2 of 7 |
| Hybrid, one query per side | 9 of 9 | 5 of 5 | 9 of 11 | 1 of 3 | 4 of 7 |

The 2 empty dev sides stay empty in every keyword run and with hybrid one query per side. A single hybrid query keeps 1 of them, with or without the first side's filter.

- The model finds sides that keyword search misses on paraphrases. Held-out sides answered go from 5 of 11 to 9 of 11.
- It also fills both sides of XH6, "How do stock option repricing rules differ for new hires and current staff?", which the playbook doesn't cover: `2.1:thresholds` for new hires, and `3:tier-1`, `3:tier-2` and `4:stale-promotion` for current staff. Keyword search leaves both sides empty. The writer would get clauses that don't answer the question, so this mode needs a relevance floor per side before the agent uses it.
- Routing the 28 single questions costs two dev hits in hybrid mode. P12, "What is the biggest stock award allowed for a top performer facing a competitor raid?", becomes a split that finds nothing, and P16, "Should people who left and candidates who said no be counted together?", becomes a new-hire question and misses `6:p1`. Held-out H3, "Who signs off on the largest retention awards?", gains `3:tier-3`. In keyword mode routing changes no hit.
- The held-out questions have now been scored once in each mode. A fix tuned on the dev questions has to say so when it reports held-out results again.

`NomicRouterRunTest` in `tests/test_cross_lever.py` replays this file and checks these results.
