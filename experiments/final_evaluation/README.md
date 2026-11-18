# Final evaluation

The files behind Section 7 of the final report, `checkpoints/checkpoint_7_1.md`. All data is synthetic. Apex Cloud & AI Corp doesn't exist.

| File | What it holds | How it is written |
| :--- | :--- | :--- |
| `scorecard.json` | Every count, section by section | `python3 -m src.evaluation.scorecard --write` |
| `scorecard.md` | The same counts in sentences, plus timing and limits | Written with the JSON |
| `live_writer_*.json` | One file per run with a real model writing the summary | `python3 -m src.evaluation.live_writer --provider auto --save experiments/final_evaluation/live_writer_NAME.json` |

## Check the scorecard

```bash
python3 -m src.evaluation.scorecard
```

The command recomputes every result with no network, prints one line per area and compares the counts with `scorecard.json`. It ends with `SCORECARD OK`, or it lists each count that changed and exits with 1. It took 14 seconds on the machine that wrote the file. Timing is the one part it leaves out of the comparison, because timing changes from machine to machine.

## What each section answers

1. `model_alone`. Can a model answer from the raw rows, or does it need the tools? Two experiments ran a real model, and their answers sit in `experiments/rows_vs_summary` and `experiments/compa_ratio_drift`. The scorecard scores those files again.
2. `one_agent_or_squad`. Does composing teams under one budget beat pricing each team alone? No model runs here. Both sides call the same tools.
3. `retrieval`. Does retrieval find the right clause for the right population? Keyword, dense and hybrid search on 28 questions, and one query per side on 12 comparisons. The embedding scores replay from `experiments/policy_retrieval`.
4. `planning`. Does the beam find what an exhaustive search finds? Beam widths 1 to 4 against all 32 plans per team, and per-team beams against 1,024 and 32,768 joint plans.
5. `guardrails`. Do the guardrails stop what they should and nothing else? The request screen on 136 frozen cases, 163 faults seeded into verified briefs, 7 trace faults and 9 invalid approvals.
6. `routing`. Where does each request end, and how often does a person have to look? 4 org briefs, 16 cohort briefs and 3 policy questions.
7. `model_prose`. Can a model's paragraph change a figure or a route? Two stand-in models take the place of the HTTP call. One copies the facts, and one adds a figure on every try.
8. `timing`. What do the controls cost in time?

## Run the model check

The scorecard uses the code-written summary. To see what the checks do with a real model's paragraph, put a key in `.env`, or set `OLLAMA_ENABLED=true`, and run:

```bash
python3 -m src.models.router --status
python3 -m src.evaluation.live_writer --provider auto --save experiments/final_evaluation/live_writer_run1.json
python3 -m src.evaluation.live_writer --replay experiments/final_evaluation/live_writer_run1.json
```

Each of the 23 requests runs twice, once with the code-written summary and once with the model. A run ends with one of four texts:

- `model_first_draft`: the model's first draft passed the fact check, the reviewer and the output check.
- `model_redraft`: a draft was rejected, and a later one passed.
- `code_after_rejection`: two tries added a number or a claim the facts don't hold, so the brief kept the code-written paragraph.
- `code_after_error`: the model gave no usable answer. It couldn't be reached, the provider returned an error, or the reply was empty. The brief kept the code-written paragraph. The command prints the provider's reason in brackets and ends with `LIVE WRITER CHECK`.

`LIVE WRITER OK` means the model answered every call and every run ended verified, on the same route as the code-written run. The saved file holds every draft, including the rejected ones and the reason for each rejection. `--replay` checks a saved file against today's checks with no model: each accepted draft must still pass, and each rejected draft must still fail.

Run this check before recording a demo. A model that gives no answer is replaced by the code-written paragraph, and the console's status card says so next to `Summary writer`. `--limit 1` sends one request, which is enough to see whether the model answers.

## What the tests pin

- `tests/test_final_evaluation.py` rebuilds the scorecard and compares it with `scorecard.json`, renders `scorecard.md` again from the JSON, and runs the fact check and the live writer check against stand-in models.
- `tests/test_final_report.py` checks that every dollar figure, percentage and N-of-M count in the final report, in the link document and on the slides appears in the scorecard.
