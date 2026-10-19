# 500 rows vs. the tool's summary

The experiment behind build log 2/7: one question, one model and two inputs, with 5 runs each. All data is synthetic. Apex Cloud & AI Corp doesn't exist.

## The question

`prompt.txt` holds the prompt. It asks how many employees in one org face a drop of 15% or more in intended cash flow from 2026 to 2027, and how many of those are high performers, meaning a 2025 rating of rating_4 or rating_5.

The right answer is 87 and 24. One SQL query over `org_roster_cashflows` gets it, and `analyze_org_cliff_and_equity_health` in `src/tools/deterministic_analytics.py` returns it as `cliff_count_gt_15pct` and `high_performer_cliff_count`.

## The two inputs

| File | What it holds | Size | Tokens in AI Studio |
| :--- | :--- | ---: | ---: |
| `org_a_rows.csv` | Org A's 500 employees, 7 columns each | 28,016 bytes | 21,030 |
| `org_a_summary.json` | The tool's output for Org A, with the org code replaced by Org A and the leader's name removed | 2,673 bytes | 1,198 |

These two commands write both files, from the repo root:

```bash
python3 -c "import csv, sqlite3; cur = sqlite3.connect('data/synthetic/comp_insight_advisor.db').execute(\"SELECT employee_id, job_family, job_level, rating_2025, intended_cashflow_2026_usd, intended_cashflow_2027_usd, yoy_cashflow_change_26_to_27_pct FROM org_roster_cashflows WHERE vp_org_code = 'VP_CLOUD_AI' ORDER BY employee_id\"); w = csv.writer(open('experiments/rows_vs_summary/org_a_rows.csv', 'w', newline='')); w.writerow([d[0] for d in cur.description]); w.writerows(cur)"
python3 -c "import json; from src.tools.deterministic_analytics import analyze_org_cliff_and_equity_health as f; r = f('VP_CLOUD_AI'); r['vp_org_code'] = r['budget_status']['vp_org_code'] = 'Org A'; r['budget_status'].pop('vp_leader_name'); json.dump(r, open('experiments/rows_vs_summary/org_a_summary.json', 'w'), indent=2)"
```

## The runs

Gemini 3.5 Flash in Google AI Studio, with the prompt and one attached file per run. `runs/` holds every answer as the model gave it.

| Run | Input | People with a drop of 15% or more | High performers among them |
| :--- | :--- | ---: | ---: |
| `rows_1` | 500 rows | 125 | 25 |
| `rows_2` | 500 rows | 111 | 23 |
| `rows_3` | 500 rows | 144 | 33 |
| `rows_4` | 500 rows | 135 | 23 |
| `rows_5` | 500 rows | 142 | 25 |
| `summary_1` to `summary_5` | Summary | 87 | 24 |

Every rows run described the right filter, a drop of at least 15% and a rating of rating_4 or rating_5, and still got both counts wrong. Every summary run read the two numbers straight from the JSON.
