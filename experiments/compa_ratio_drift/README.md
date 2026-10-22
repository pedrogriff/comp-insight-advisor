# Compa-ratio drift

How often does a language model get a compa-ratio wrong when it does the division in text, and does a divide tool fix it? This experiment measures both on 300 synthetic employees.

All data is synthetic. Apex Cloud & AI Corp doesn't exist.

## What it does

- Samples 300 employees from `org_roster_cashflows` with `random.Random(42)` and gives them placeholder IDs, E001 to E300. The model sees only the ID, `base_salary_usd` and `market_reference_usd`.
- The true answer is `round(base_salary_usd / market_reference_usd, 3)`, which equals the stored `compa_ratio` on every row.
- 25 of the 300 sit within 0.005 of 0.90, 1.00 or 1.10, where a small error moves someone into another bracket.
- Two setups, 5 runs each per model:
  - `text`: one prompt with the 300 rows as CSV, asking for a CSV of compa-ratios to 3 decimals.
  - `tool`: the same prompt plus a `divide(a, b)` tool that returns the quotient rounded to 3 decimals, with an instruction to call it for every row and copy the result.
- Each model runs at its default temperature. The script never sends one.

## Run it

Python 3.10 or newer, standard library only. From the repo root:

```bash
python3 experiments/compa_ratio_drift/drift.py sample

export GEMINI_API_KEY=your-key-from-google-ai-studio
python3 experiments/compa_ratio_drift/drift.py run --provider gemini --model MODEL --setup text
python3 experiments/compa_ratio_drift/drift.py run --provider gemini --model MODEL --setup tool

python3 experiments/compa_ratio_drift/drift.py run --provider ollama --model qwen2.5:7b --setup text --batch-size 50
python3 experiments/compa_ratio_drift/drift.py run --provider ollama --model qwen2.5:7b --setup tool --batch-size 50

python3 experiments/compa_ratio_drift/drift.py summarize
```

- `MODEL` is a Flash-tier model name from the AI Studio model list. `--provider openrouter` with `OPENROUTER_API_KEY` works the same way.
- For Ollama, pick a model whose `ollama show` output lists tools. `--batch-size 50` sends six conversations of 50 rows each, for models that can't handle 300 rows or 300 tool calls at once. Say so when you report the result.
- Each `run` adds 5 runs by default. Run it again and it continues the numbering.
- On rate limits the script retries with backoff, and `--pause 5` waits 5 seconds before every request.
- `summarize --usd-per-mtok-in X --usd-per-mtok-out Y` adds a cost per run from the token counts.
- `rsvg-convert -o results/chart.png results/chart.svg` or `magick results/chart.svg results/chart.png` turns the chart into a PNG.

## Files

| Path | What it holds |
| :--- | :--- |
| `sample.csv`, `truth.csv` | The 300 rows the model sees, and the true compa-ratios with each row's employee ID |
| `prompt_text.txt`, `prompt_tool.txt` | The two full prompts |
| `results/<provider>_<model>/<setup>/run_N.json` | Every reply, the full conversation, token counts and timing for run N |
| `results/<provider>_<model>/<setup>/run_N.csv` | The compa-ratios the model returned in run N |
| `results/summary.csv` | The measures for every run |
| `results/summary_by_setup.csv` | Medians per model and setup, and how many IDs the runs disagree on |
| `results/chart.svg` | Median exact matches per model, text-only in red and the tool in green, 1080 by 1350 |

## Measures per run

| Measure | Definition |
| :--- | :--- |
| Exact | The returned value equals the true value to 3 decimals |
| Off by more than 0.005 | Absolute error above 0.005 |
| Worst miss | Largest absolute error |
| Dropped, duplicated | IDs missing from the answer, or listed more than once |
| Bracket flips | The true and returned values fall in different brackets: below 0.90, 0.90 to under 1.00, 1.00 to under 1.10, and 1.10 or above |
| Runs disagree | IDs where a model's runs in one setup don't all return the same value |
| Tokens | Prompt and completion tokens from the API responses |

The answer parser reads only lines with exactly two fields, an ID and a number, so rows a model echoes from the input never count as answers.
