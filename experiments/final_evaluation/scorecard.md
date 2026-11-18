# Final evaluation scorecard

`python3 -m src.evaluation.scorecard --write` wrote this file from `scorecard.json`. Every count comes from code run on the committed synthetic data. No model ran, apart from the two recorded baselines, whose answers sit in `experiments/rows_vs_summary` and `experiments/compa_ratio_drift`.

| Area | Result |
| :--- | :--- |
| A model alone, counting | Given 500 rows, the model got a two-number count right in 0 of 5 runs. Given the tool's summary, it was right in 5 of 5. |
| A model alone, dividing | Dividing in text, the model matched the stored compa-ratio for a median of 297 of 300 employees. With a divide tool it matched 300 of 300. |
| Composing teams under one budget | The one-agent baseline prices each team alone, and its plans add up to $3,246,000, $1,096,000 over the $2,150,000 budget. The squad's joint plan costs $1,995,600 and addresses 7 of 11 departures and 16 of 16 declined offers. |
| Policy retrieval | The right clause is in the top 3 for 11 of 24 questions with keyword search, 24 of 24 with dense search and 23 of 24 with hybrid search. On the 4 questions the playbook does not cover, keyword search returned nothing for 4 of 4, dense search for 3 of 4 and hybrid search for 3 of 4. |
| Comparisons across populations | On held-out comparisons, one query per side answers 9 of 11 sides with hybrid search, against 5 of 11 for a single query. With keyword search it is 5 of 11 against 0 of 11. |
| Planning, one team | Beam width 3 returned 9 of 9 options and 15 of 15 Pareto plans, and stayed right at 105 of 105 budget levels. It plans 30 critic reviews against 93 for exhaustive search, 67.7% fewer. |
| Planning, several teams | Per-team beams plus composition priced 85 of 1,024 joint plans for two teams and 320 of 32,768 for three, and matched the exhaustive options both times. |
| Request screen | The screen refused 0 of 50 benign requests. On the split written apart from the rules and scored once, it decided 40 of 48 right and let 8 of 30 violations through. |
| Containment | 10 violations passed the screen across all splits, and the scoped tools, the verifier and the approval route contained 10 of 10. |
| Verifier and output check | 23 of 23 clean briefs pass, and the checks reject 158 of 163 seeded faults. The 5 misses are invented percentages that match a figure elsewhere in the tool output. |
| Monitor and approval gate | The monitor flagged 7 of 7 seeded trace faults, and the gate refused 9 of 9 invalid decisions. |
| Routing | 18 of 23 requests were released without a person and 5 of 23 waited for sign-off, 21.7%. 0 of 23 were held. |
| A model's paragraph | A stand-in model that copies the facts had 23 of 23 first drafts accepted. One that invents a figure in every draft ended 23 of 23 runs on the code-written paragraph, and 23 of 23 kept the route of the code-written run. |

## Timing on the machine that wrote this file

A guarded run takes a median of 175.3 ms against 91.7 ms for the squad alone, so the controls add 83.5 ms. A refusal takes 1.9 ms. Across all requests the median is 63.8 ms and the slowest is 165.4 ms. These runs use the code-written summary, so they leave out the seconds a model takes to write.

## What this scorecard does not show

- All data is synthetic, and every test case was written for this project. The held-out splits were frozen before the code they test was tuned, and the request screen's last split was written from the policy alone and scored once.
- No compensation partner has used the advisor, so nothing here measures whether a brief helps a decision.
- The two model baselines are 10 runs on one model and 8 runs on another. They show that the failure exists, not how often it happens across models.
- A model's paragraph appears here only through stand-in models. `python3 -m src.evaluation.live_writer` runs a real one, and its saved runs sit next to this file.
