"""Compa-ratio drift experiment.

Does a language model get compa-ratios right when it does the division in text, and does a
divide tool fix it? The script samples 300 synthetic employees with a fixed seed, asks a model
for every compa-ratio in two setups, and scores each run against the true values.

From the repo root:
    python3 experiments/compa_ratio_drift/drift.py sample
    python3 experiments/compa_ratio_drift/drift.py run --provider gemini --model MODEL --setup text
    python3 experiments/compa_ratio_drift/drift.py run --provider gemini --model MODEL --setup tool
    python3 experiments/compa_ratio_drift/drift.py summarize

Standard library only. README.md in this folder explains the setups and the measures.
"""

import argparse
import csv
import json
import os
import random
import re
import sqlite3
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB_PATH = HERE.parent.parent / "data" / "synthetic" / "comp_insight_advisor.db"
RESULTS_DIR = HERE / "results"
SEED = 42
SAMPLE_SIZE = 300
BOUNDARIES = (0.90, 1.00, 1.10)
NEAR = 0.005
PROVIDERS = {
    # name: (default base URL, API key variable, wire format)
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/", "GEMINI_API_KEY", "openai"),
    "openrouter": ("https://openrouter.ai/api/v1/", "OPENROUTER_API_KEY", "openai"),
    "ollama": ("http://localhost:11434/", None, "ollama"),
}
DIVIDE_TOOL = {
    "type": "function",
    "function": {
        "name": "divide",
        "description": "Divides a by b and returns the quotient rounded to 3 decimals.",
        "parameters": {
            "type": "object",
            "properties": {
                "a": {"type": "number", "description": "The dividend, base_salary_usd"},
                "b": {"type": "number", "description": "The divisor, market_reference_usd"},
            },
            "required": ["a", "b"],
        },
    },
}
INTRO = ("Below are {n} employees as CSV. For each one, compute the compa-ratio, which is "
         "base_salary_usd divided by market_reference_usd, rounded to 3 decimals.\n\n")
TASKS = {
    "text": "Do the division yourself.",
    "tool": ("Call the divide tool once for every employee, with a = base_salary_usd and "
             "b = market_reference_usd, and copy the result it returns. Don't compute anything yourself."),
}
OUTRO = (" Then return only CSV with the header id,compa_ratio and one line per employee, in the same "
         "order. No other text.\n\n")


def build_sample(db_path=DB_PATH):
    """Draws the 300-row sample with a fixed seed. Each row carries its true compa-ratio."""
    with closing(sqlite3.connect(db_path)) as conn:
        rows = conn.execute("SELECT employee_id, base_salary_usd, market_reference_usd "
                            "FROM org_roster_cashflows ORDER BY employee_id").fetchall()
    sample = []
    for i, (employee_id, base, market) in enumerate(random.Random(SEED).sample(rows, SAMPLE_SIZE), 1):
        ratio = base / market
        sample.append({
            "id": f"E{i:03d}",
            "employee_id": employee_id,
            "base_salary_usd": int(base) if float(base).is_integer() else base,
            "market_reference_usd": int(market) if float(market).is_integer() else market,
            "true_ratio": round(ratio, 3),
            "near_boundary": any(abs(ratio - b) < NEAR for b in BOUNDARIES),
        })
    return sample


def bracket(value):
    """0 is below 0.90, 1 is 0.90 to under 1.00, 2 is 1.00 to under 1.10, 3 is 1.10 or above."""
    return sum(value >= b for b in BOUNDARIES)


def divide(a, b):
    return round(float(a) / float(b), 3)


def build_prompt(rows, setup):
    lines = ["id,base_salary_usd,market_reference_usd"]
    lines += [f"{r['id']},{r['base_salary_usd']},{r['market_reference_usd']}" for r in rows]
    return INTRO.format(n=len(rows)) + TASKS[setup] + OUTRO + "\n".join(lines) + "\n"


ID_RE = re.compile(r"^E\d{3}$")
NUMBER_RE = re.compile(r"^-?\d*\.?\d+$")


def parse_predictions(text):
    """Reads id,value pairs from a model's answer. Lines with more than two fields are skipped,
    so rows the model echoes from the input never count as answers."""
    pairs = []
    for line in (text or "").splitlines():
        fields = [f.strip("`*") for f in re.split(r"[,;|\t]|\s+", line.strip().strip("|"))]
        fields = [f for f in fields if f]
        if len(fields) == 2 and ID_RE.match(fields[0]) and NUMBER_RE.match(fields[1]):
            pairs.append((fields[0], float(fields[1])))
    return pairs


def first_values(pairs):
    values = {}
    for id_, value in pairs:
        values.setdefault(id_, value)
    return values


def score(pairs, truth):
    """Scores one run. truth maps each id to its true compa-ratio."""
    got, duplicated, unknown = {}, 0, 0
    for id_, value in pairs:
        if id_ not in truth:
            unknown += 1
        elif id_ in got:
            duplicated += 1
        else:
            got[id_] = value
    errors = {i: abs(v - truth[i]) for i, v in got.items()}
    return {
        "returned": len(got),
        "exact": sum(e < 1e-9 for e in errors.values()),
        "off_by_more_than_0005": sum(e > NEAR + 1e-9 for e in errors.values()),
        "worst_miss": round(max(errors.values()), 6) if errors else "",
        "dropped": len(truth) - len(got),
        "duplicated": duplicated,
        "unknown_ids": unknown,
        "bracket_flips": sum(bracket(v) != bracket(truth[i]) for i, v in got.items()),
    }


def disagreement(runs, ids):
    """Counts ids where the runs don't all return the same value. A missing value counts as a value."""
    return sum(len({run.get(i) for run in runs}) > 1 for i in ids)


def _arguments(raw):
    if isinstance(raw, dict):
        return raw
    try:
        value = json.loads(raw or "{}")
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return {}


def _ollama_messages(messages):
    names, converted = {}, []
    for m in messages:
        if m["role"] == "assistant" and m.get("tool_calls"):
            calls = []
            for c in m["tool_calls"]:
                names[c["id"]] = c["function"]["name"]
                calls.append({"function": {"name": c["function"]["name"],
                                           "arguments": _arguments(c["function"]["arguments"])}})
            converted.append({"role": "assistant", "content": m.get("content") or "", "tool_calls": calls})
        elif m["role"] == "tool":
            converted.append({"role": "tool", "content": m["content"], "tool_name": names.get(m["tool_call_id"], "")})
        else:
            converted.append({"role": m["role"], "content": m["content"]})
    return converted


class ChatClient:
    """Talks to an OpenAI-compatible endpoint, such as Gemini or OpenRouter, or to Ollama's own API."""

    def __init__(self, provider, model, base_url=None, api_key=None, num_ctx=16384, timeout=900,
                 retries=5, pause=0.0):
        default_url, key_var, self.wire = PROVIDERS[provider]
        self.provider, self.model, self.num_ctx = provider, model, num_ctx
        self.base_url = (base_url or default_url).rstrip("/") + "/"
        self.api_key = api_key if api_key is not None else (os.environ.get(key_var, "") if key_var else "")
        if key_var and not self.api_key:
            raise SystemExit(f"Set {key_var} first, for example: export {key_var}=...")
        self.timeout, self.retries, self.pause = timeout, retries, pause
        host = urllib.parse.urlsplit(self.base_url).hostname
        # A local server, such as Ollama, is reached directly even when a proxy is configured.
        local = host in ("localhost", "127.0.0.1", "::1")
        self._open = urllib.request.build_opener(urllib.request.ProxyHandler({})).open if local else urllib.request.urlopen

    def _post(self, path, body):
        data = json.dumps(body).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key
        url = self.base_url + path
        for attempt in range(self.retries + 1):
            try:
                request = urllib.request.Request(url, data=data, headers=headers, method="POST")
                with self._open(request, timeout=self.timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", "replace")[:500]
                if exc.code in (429, 500, 502, 503, 504) and attempt < self.retries:
                    time.sleep(2 ** (attempt + 1))
                    continue
                raise RuntimeError(f"HTTP {exc.code} from {url}: {detail}") from None
            except urllib.error.URLError as exc:
                if attempt < self.retries:
                    time.sleep(2 ** (attempt + 1))
                    continue
                raise RuntimeError(f"Can't reach {url}: {exc.reason}") from None

    def chat(self, messages, tools=None):
        """Returns the reply text, its tool calls and its token counts."""
        if self.pause:
            time.sleep(self.pause)
        if self.wire == "openai":
            body = {"model": self.model, "messages": messages}
            if tools:
                body["tools"] = tools
            raw = self._post("chat/completions", body)
            message = raw["choices"][0]["message"]
            usage = raw.get("usage") or {}
            calls = [{"id": c.get("id") or f"call_{n}", "name": c["function"]["name"],
                      "arguments": _arguments(c["function"].get("arguments"))}
                     for n, c in enumerate(message.get("tool_calls") or [])]
            return {"content": message.get("content") or "", "tool_calls": calls, "raw": raw,
                    "prompt_tokens": usage.get("prompt_tokens") or 0,
                    "completion_tokens": usage.get("completion_tokens") or 0}
        body = {"model": self.model, "messages": _ollama_messages(messages), "stream": False,
                "options": {"num_ctx": self.num_ctx, "num_predict": 8192}}
        if tools:
            body["tools"] = tools
        raw = self._post("api/chat", body)
        message = raw.get("message") or {}
        calls = [{"id": f"call_{n}", "name": c["function"]["name"],
                  "arguments": _arguments(c["function"].get("arguments"))}
                 for n, c in enumerate(message.get("tool_calls") or [])]
        return {"content": message.get("content") or "", "tool_calls": calls, "raw": raw,
                "prompt_tokens": raw.get("prompt_eval_count") or 0,
                "completion_tokens": raw.get("eval_count") or 0}


def call_tool(call):
    if call["name"] != "divide":
        return "error: unknown tool " + call["name"]
    try:
        return f"{divide(call['arguments']['a'], call['arguments']['b']):.3f}"
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
        return "error: " + exc.__class__.__name__


def run_conversation(client, rows, setup, max_turns=60):
    """One conversation over one batch of rows. In the tool setup, every divide call is answered
    until the model replies with text or the turn cap is reached."""
    messages = [{"role": "user", "content": build_prompt(rows, setup)}]
    tools = [DIVIDE_TOOL] if setup == "tool" else None
    out = {"rows": len(rows), "turns": 0, "tool_calls": 0, "prompt_tokens": 0, "completion_tokens": 0,
           "hit_turn_cap": False, "answer": "", "responses": []}
    while True:
        if out["turns"] == max_turns:
            out["hit_turn_cap"] = True
            break
        reply = client.chat(messages, tools)
        out["turns"] += 1
        out["prompt_tokens"] += reply["prompt_tokens"]
        out["completion_tokens"] += reply["completion_tokens"]
        out["responses"].append(reply["raw"])
        if not (tools and reply["tool_calls"]):
            out["answer"] = reply["content"]
            break
        messages.append({"role": "assistant", "content": reply["content"] or None, "tool_calls": [
            {"id": c["id"], "type": "function",
             "function": {"name": c["name"], "arguments": json.dumps(c["arguments"])}}
            for c in reply["tool_calls"]]})
        for c in reply["tool_calls"]:
            messages.append({"role": "tool", "tool_call_id": c["id"], "content": call_tool(c)})
            out["tool_calls"] += 1
    out["messages"] = messages
    return out


def slug(text):
    return re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-")


def write_sample_files(sample, folder=HERE):
    with open(folder / "sample.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["id", "base_salary_usd", "market_reference_usd"])
        w.writerows([r["id"], r["base_salary_usd"], r["market_reference_usd"]] for r in sample)
    with open(folder / "truth.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["id", "employee_id", "compa_ratio", "near_boundary"])
        w.writerows([r["id"], r["employee_id"], f"{r['true_ratio']:.3f}", int(r["near_boundary"])]
                    for r in sample)
    for setup in TASKS:
        (folder / f"prompt_{setup}.txt").write_text(build_prompt(sample, setup), encoding="utf-8")


def run_experiment(client, setup, runs, batch_size, max_turns, results_dir=RESULTS_DIR):
    sample = build_sample()
    truth = {r["id"]: r["true_ratio"] for r in sample}
    folder = Path(results_dir) / slug(f"{client.provider}_{client.model}") / setup
    folder.mkdir(parents=True, exist_ok=True)
    done = sorted(int(p.stem.split("_")[1]) for p in folder.glob("run_*.json"))
    first = done[-1] + 1 if done else 1
    for n in range(first, first + runs):
        started = time.time()
        batches = [run_conversation(client, sample[i:i + batch_size], setup, max_turns)
                   for i in range(0, len(sample), batch_size)]
        record = {"provider": client.provider, "model": client.model, "setup": setup, "run": n,
                  "batch_size": batch_size, "temperature": "model default, not sent",
                  "base_url": client.base_url, "started_utc": datetime.now(timezone.utc).isoformat(),
                  "seconds": round(time.time() - started, 1), "batches": batches}
        (folder / f"run_{n}.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
        pairs = parse_predictions("\n".join(b["answer"] for b in batches))
        with open(folder / f"run_{n}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(["id", "compa_ratio"])
            w.writerows(pairs)
        m = score(pairs, truth)
        print(f"{client.model} {setup} run {n}: {m['exact']} of {len(truth)} exact, "
              f"{m['off_by_more_than_0005']} off by more than 0.005, {m['dropped']} dropped, "
              f"{m['duplicated']} duplicated, {m['bracket_flips']} bracket flips, {record['seconds']} s",
              flush=True)


def summarize(results_dir=RESULTS_DIR, usd_in=0.0, usd_out=0.0):
    """Writes summary.csv per run, summary_by_setup.csv per model and setup, and chart.svg."""
    results_dir = Path(results_dir)
    sample = build_sample()
    truth = {r["id"]: r["true_ratio"] for r in sample}
    rows, groups = [], {}
    paths = sorted(results_dir.glob("*/*/run_*.json"),
                   key=lambda p: (p.parent.parent.name, p.parent.name, int(p.stem.split("_")[1])))
    for path in paths:
        rec = json.loads(path.read_text(encoding="utf-8"))
        pairs = parse_predictions("\n".join(b["answer"] for b in rec["batches"]))
        row = {"provider": rec["provider"], "model": rec["model"], "setup": rec["setup"], "run": rec["run"],
               "batch_size": rec["batch_size"], **score(pairs, truth),
               "tool_calls": sum(b["tool_calls"] for b in rec["batches"]),
               "turns": sum(b["turns"] for b in rec["batches"]),
               "hit_turn_cap": any(b["hit_turn_cap"] for b in rec["batches"]),
               "prompt_tokens": sum(b["prompt_tokens"] for b in rec["batches"]),
               "completion_tokens": sum(b["completion_tokens"] for b in rec["batches"]),
               "seconds": rec["seconds"]}
        row["cost_usd"] = (round((row["prompt_tokens"] * usd_in + row["completion_tokens"] * usd_out) / 1e6, 4)
                           if usd_in or usd_out else "")
        rows.append(row)
        groups.setdefault((rec["provider"], rec["model"], rec["setup"]), []).append((row, first_values(pairs)))
    if not rows:
        raise SystemExit(f"No runs found under {results_dir}. Run the run command first.")
    _write_rows(results_dir / "summary.csv", rows)
    by_setup = []
    for (provider, model, setup), items in groups.items():
        exact = [r["exact"] for r, _ in items]
        by_setup.append({
            "provider": provider, "model": model, "setup": setup, "runs": len(items),
            "exact_median": statistics.median(exact), "exact_min": min(exact), "exact_max": max(exact),
            "off_by_more_than_0005_median": statistics.median(r["off_by_more_than_0005"] for r, _ in items),
            "worst_miss": max((r["worst_miss"] for r, _ in items if r["worst_miss"] != ""), default=""),
            "dropped_or_duplicated_max": max(r["dropped"] + r["duplicated"] for r, _ in items),
            "bracket_flips_median": statistics.median(r["bracket_flips"] for r, _ in items),
            "ids_where_runs_disagree": disagreement([v for _, v in items], list(truth)),
            "tool_calls_median": statistics.median(r["tool_calls"] for r, _ in items),
            "tokens_per_run_median": statistics.median(r["prompt_tokens"] + r["completion_tokens"]
                                                       for r, _ in items),
            "seconds_median": statistics.median(r["seconds"] for r, _ in items),
        })
    _write_rows(results_dir / "summary_by_setup.csv", by_setup)
    (results_dir / "chart.svg").write_text(chart_svg(by_setup, len(truth)), encoding="utf-8")
    near = sum(r["near_boundary"] for r in sample)
    print(f"{near} of the {len(sample)} employees sit within {NEAR} of 0.90, 1.00 or 1.10.")
    for s in by_setup:
        print(f"{s['model']} {s['setup']}: {s['runs']} runs, exact median {s['exact_median']} "
              f"({s['exact_min']} to {s['exact_max']}), off by more than 0.005 median "
              f"{s['off_by_more_than_0005_median']}, worst miss {s['worst_miss']}, dropped or duplicated "
              f"up to {s['dropped_or_duplicated_max']}, bracket flips median {s['bracket_flips_median']}, "
              f"runs disagree on {s['ids_where_runs_disagree']} ids, tokens per run {s['tokens_per_run_median']}")
    return rows, by_setup


def _write_rows(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def _esc(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "")


def chart_svg(by_setup, total):
    """A 1080 x 1350 bar chart: median exact matches per model, text-only in red, tool in green.
    Filled shapes only and no straight double quotes in text, so ImageMagick renders it as drawn."""
    models = list(dict.fromkeys(s["model"] for s in by_setup))
    values = {(s["model"], s["setup"]): s for s in by_setup}
    top, base_y, left, width = 300, 1050, 90, 900
    scale = (base_y - top) / total
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1350" viewBox="0 0 1080 1350">',
             '<rect width="1080" height="1350" fill="#0B1220"/>',
             '<text x="90" y="130" font-family="Roboto, sans-serif" font-size="64" font-weight="700" '
             f'fill="#F9FAFB">Exact compa-ratios out of {total}</text>',
             '<text x="90" y="190" font-family="Roboto, sans-serif" font-size="32" fill="#9CA3AF">'
             'Synthetic data. Median run for each setup.</text>',
             f'<rect x="{left}" y="{top - 2}" width="{width}" height="4" fill="#1F2937"/>',
             f'<rect x="{left}" y="{base_y}" width="{width}" height="4" fill="#60A5FA"/>']
    group = width / max(len(models), 1)
    for i, model in enumerate(models):
        cx = left + group * i + group / 2
        for j, (setup, color) in enumerate((("text", "#F87171"), ("tool", "#34D399"))):
            s = values.get((model, setup))
            if not s:
                continue
            height = s["exact_median"] * scale
            x = cx - 160 + j * 170
            parts.append(f'<rect x="{x:.0f}" y="{base_y - height:.0f}" width="150" height="{height:.0f}" '
                         f'fill="{color}"/>')
            parts.append(f'<text x="{x + 75:.0f}" y="{base_y - height - 20:.0f}" text-anchor="middle" '
                         f'font-family="Roboto, sans-serif" font-size="44" font-weight="700" fill="#F9FAFB">'
                         f'{_esc(s["exact_median"])}</text>')
        parts.append(f'<text x="{cx:.0f}" y="{base_y + 60}" text-anchor="middle" font-family="Roboto, sans-serif" '
                     f'font-size="30" fill="#E5E7EB">{_esc(model)}</text>')
    legend_y = base_y + 140
    for k, (label, color) in enumerate((("Text-only math", "#F87171"), ("Divide tool", "#34D399"))):
        x = left + k * 420
        parts.append(f'<rect x="{x}" y="{legend_y - 30}" width="36" height="36" fill="{color}"/>')
        parts.append(f'<text x="{x + 52}" y="{legend_y}" font-family="Roboto, sans-serif" font-size="32" '
                     f'fill="#E5E7EB">{label}</text>')
    parts.append('<text x="90" y="1300" font-family="Roboto, sans-serif" font-size="28" fill="#9CA3AF">'
                 'Models write the words. Code computes the money. People decide.</text>')
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Compa-ratio drift experiment on synthetic data.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("sample", help="write sample.csv, truth.csv and the two full prompts")
    run = sub.add_parser("run", help="run one model in one setup")
    run.add_argument("--provider", choices=sorted(PROVIDERS), required=True)
    run.add_argument("--model", required=True)
    run.add_argument("--setup", choices=sorted(TASKS), required=True)
    run.add_argument("--runs", type=int, default=5)
    run.add_argument("--batch-size", type=int, default=SAMPLE_SIZE,
                     help="rows per conversation. Use 50 if a model can't handle all 300 at once")
    run.add_argument("--max-turns", type=int, default=60, help="tool setup: replies per conversation")
    run.add_argument("--base-url", help="override the provider's default endpoint")
    run.add_argument("--num-ctx", type=int, default=16384, help="Ollama context window in tokens")
    run.add_argument("--pause", type=float, default=0.0, help="seconds to wait before each request")
    run.add_argument("--results", default=str(RESULTS_DIR))
    summary = sub.add_parser("summarize", help="score every run and write the summaries and chart")
    summary.add_argument("--results", default=str(RESULTS_DIR))
    summary.add_argument("--usd-per-mtok-in", type=float, default=0.0)
    summary.add_argument("--usd-per-mtok-out", type=float, default=0.0)
    args = parser.parse_args()
    if args.command == "sample":
        sample = build_sample()
        write_sample_files(sample)
        print(f"Wrote sample.csv, truth.csv, prompt_text.txt and prompt_tool.txt. "
              f"{sum(r['near_boundary'] for r in sample)} of {len(sample)} sit within {NEAR} of a boundary.")
    elif args.command == "run":
        client = ChatClient(args.provider, args.model, args.base_url, num_ctx=args.num_ctx, pause=args.pause)
        run_experiment(client, args.setup, args.runs, args.batch_size, args.max_turns, args.results)
    else:
        summarize(args.results, args.usd_per_mtok_in, args.usd_per_mtok_out)


if __name__ == "__main__":
    main()
