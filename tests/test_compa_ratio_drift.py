"""Unit tests for the compa-ratio drift experiment. Standard library only, no network."""

from contextlib import closing, redirect_stdout
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import io
import json
import re
import sqlite3
import sys
import tempfile
import threading
import unittest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from experiments.compa_ratio_drift import drift  # noqa: E402


class SampleTest(unittest.TestCase):

    def test_sample_is_fixed_and_matches_the_stored_compa_ratio(self):
        sample = drift.build_sample()
        self.assertEqual(len(sample), 300)
        self.assertEqual([r["id"] for r in sample[:2]], ["E001", "E002"])
        self.assertEqual(sample[-1]["id"], "E300")
        self.assertEqual([r["employee_id"] for r in sample[:3]], ["EMP11310", "EMP10229", "EMP10052"])
        self.assertEqual(len({r["employee_id"] for r in sample}), 300)
        self.assertEqual(sum(r["near_boundary"] for r in sample), 25)
        with closing(sqlite3.connect(drift.DB_PATH)) as conn:
            stored = dict(conn.execute("SELECT employee_id, compa_ratio FROM org_roster_cashflows"))
        for r in sample:
            self.assertEqual(r["true_ratio"], round(r["base_salary_usd"] / r["market_reference_usd"], 3))
            self.assertEqual(r["true_ratio"], stored[r["employee_id"]])

    def test_full_table_has_158_rows_near_a_bracket_line(self):
        with closing(sqlite3.connect(drift.DB_PATH)) as conn:
            rows = conn.execute("SELECT base_salary_usd, market_reference_usd FROM org_roster_cashflows").fetchall()
        near = sum(any(abs(b / m - x) < drift.NEAR for x in drift.BOUNDARIES) for b, m in rows)
        self.assertEqual((len(rows), near), (2000, 158))

    def test_prompts_differ_only_in_the_task_line(self):
        rows = drift.build_sample()[:2]
        text, tool = drift.build_prompt(rows, "text"), drift.build_prompt(rows, "tool")
        self.assertIn("Do the division yourself.", text)
        self.assertIn("Call the divide tool once for every employee", tool)
        self.assertTrue(text.endswith(f"E002,{rows[1]['base_salary_usd']},{rows[1]['market_reference_usd']}\n"))
        self.assertEqual(text.split("\n\n")[-1], tool.split("\n\n")[-1])


class ParseAndScoreTest(unittest.TestCase):

    def test_parse_skips_echoed_rows_headers_and_formatting(self):
        text = "```csv\nid,compa_ratio\nE001,0.933\n| E002 | 0.926 |\nE003,212700,228000\nE004 0.9\n```"
        self.assertEqual(drift.parse_predictions(text), [("E001", 0.933), ("E002", 0.926), ("E004", 0.9)])

    def test_score_counts_each_measure(self):
        truth = {"E001": 0.933, "E002": 0.899, "E003": 1.0, "E004": 0.95}
        pairs = [("E001", 0.933), ("E002", 0.9), ("E002", 0.5), ("E003", 0.99), ("E009", 1.0)]
        self.assertEqual(drift.score(pairs, truth), {
            "returned": 3, "exact": 1, "off_by_more_than_0005": 1, "worst_miss": 0.01, "dropped": 1,
            "duplicated": 1, "unknown_ids": 1, "bracket_flips": 2})

    def test_brackets_and_divide(self):
        self.assertEqual([drift.bracket(v) for v in (0.899, 0.9, 0.999, 1.0, 1.099, 1.1)], [0, 1, 1, 2, 2, 3])
        self.assertEqual(drift.divide(212700, 228000), 0.933)
        self.assertEqual(drift.call_tool({"name": "divide", "arguments": {"a": 212700, "b": 228000}}), "0.933")
        self.assertEqual(drift.call_tool({"name": "divide", "arguments": {"a": 1}}), "error: KeyError")

    def test_disagreement_counts_missing_values_as_different(self):
        runs = [{"E001": 0.9, "E002": 1.0}, {"E001": 0.9, "E002": 1.01}, {"E001": 0.9}]
        self.assertEqual(drift.disagreement(runs, ["E001", "E002", "E003"]), 1)
        self.assertEqual(drift.disagreement(runs[:1] * 3, ["E001", "E002"]), 0)


class FakeEndpoint:
    """A local HTTP server that answers chat requests with a test's respond(path, body) function."""

    def __init__(self, respond):
        self.requests = []
        endpoint = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                endpoint.requests.append((self.path, body, self.headers.get("Authorization")))
                data = json.dumps(respond(self.path, body)).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/v1/"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class ClientTest(unittest.TestCase):

    def endpoint(self, respond):
        fake = FakeEndpoint(respond)
        self.addCleanup(fake.close)
        return fake

    def test_text_setup_sends_no_tools_and_counts_tokens(self):
        rows = drift.build_sample()[:3]
        answer = "id,compa_ratio\n" + "\n".join(f"{r['id']},{r['true_ratio']:.3f}" for r in rows)
        fake = self.endpoint(lambda path, body: {
            "choices": [{"message": {"content": answer}}], "usage": {"prompt_tokens": 50, "completion_tokens": 20}})
        client = drift.ChatClient("openrouter", "test-model", base_url=fake.url, api_key="test-key", retries=0)
        out = drift.run_conversation(client, rows, "text")
        path, body, auth = fake.requests[0]
        self.assertEqual((path, auth, "tools" in body), ("/v1/chat/completions", "Bearer test-key", False))
        self.assertEqual((out["turns"], out["prompt_tokens"], out["completion_tokens"]), (1, 50, 20))
        truth = {r["id"]: r["true_ratio"] for r in rows}
        self.assertEqual(drift.score(drift.parse_predictions(out["answer"]), truth)["exact"], 3)

    def test_tool_setup_answers_every_call_before_the_final_reply(self):
        rows = drift.build_sample()[:4]

        def respond(path, body):
            results = [m for m in body["messages"] if m["role"] == "tool"]
            if not results:
                return {"choices": [{"message": {"content": None, "tool_calls": [
                    {"id": f"c{n}", "type": "function", "function": {"name": "divide", "arguments": json.dumps(
                        {"a": r["base_salary_usd"], "b": r["market_reference_usd"]})}}
                    for n, r in enumerate(rows)]}}], "usage": {"prompt_tokens": 100, "completion_tokens": 40}}
            lines = [f"{r['id']},{m['content']}" for r, m in zip(rows, results)]
            return {"choices": [{"message": {"content": "id,compa_ratio\n" + "\n".join(lines)}}],
                    "usage": {"prompt_tokens": 180, "completion_tokens": 30}}

        fake = self.endpoint(respond)
        client = drift.ChatClient("gemini", "test-model", base_url=fake.url, api_key="test-key", retries=0)
        out = drift.run_conversation(client, rows, "tool")
        self.assertEqual((out["turns"], out["tool_calls"], out["prompt_tokens"]), (2, 4, 280))
        second = fake.requests[1][1]["messages"]
        self.assertEqual([m["content"] for m in second if m["role"] == "tool"],
                         [f"{r['true_ratio']:.3f}" for r in rows])
        self.assertEqual(fake.requests[0][1]["tools"][0]["function"]["name"], "divide")
        truth = {r["id"]: r["true_ratio"] for r in rows}
        self.assertEqual(drift.score(drift.parse_predictions(out["answer"]), truth)["exact"], 4)

    def test_ollama_wire_sends_context_size_and_tool_names(self):
        rows = drift.build_sample()[:2]

        def respond(path, body):
            if not any(m["role"] == "tool" for m in body["messages"]):
                return {"message": {"role": "assistant", "content": "", "tool_calls": [
                    {"function": {"name": "divide", "arguments": {"a": r["base_salary_usd"],
                                                                  "b": r["market_reference_usd"]}}}
                    for r in rows]}, "prompt_eval_count": 10, "eval_count": 5}
            return {"message": {"role": "assistant", "content": "E001,0.5\nE002,0.5"},
                    "prompt_eval_count": 20, "eval_count": 6}

        fake = self.endpoint(respond)
        client = drift.ChatClient("ollama", "local-model", base_url=fake.url.replace("/v1/", "/"), retries=0)
        out = drift.run_conversation(client, rows, "tool")
        path, body, auth = fake.requests[1]
        self.assertEqual((path, auth, body["options"]["num_ctx"], body["stream"]), ("/api/chat", None, 16384, False))
        assistant = [m for m in body["messages"] if m["role"] == "assistant"][0]
        self.assertIsInstance(assistant["tool_calls"][0]["function"]["arguments"], dict)
        self.assertEqual([m["tool_name"] for m in body["messages"] if m["role"] == "tool"], ["divide", "divide"])
        self.assertEqual((out["turns"], out["tool_calls"], out["completion_tokens"]), (2, 2, 11))

    def test_turn_cap_is_recorded(self):
        fake = self.endpoint(lambda path, body: {"choices": [{"message": {"content": None, "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "divide", "arguments": '{"a": 1, "b": 2}'}}]}}]})
        client = drift.ChatClient("openrouter", "test-model", base_url=fake.url, api_key="test-key", retries=0)
        out = drift.run_conversation(client, drift.build_sample()[:1], "tool", max_turns=2)
        self.assertEqual((out["hit_turn_cap"], out["answer"], out["tool_calls"]), (True, "", 2))

    def test_missing_api_key_stops_with_a_clear_message(self):
        with self.assertRaises(SystemExit) as ctx:
            drift.ChatClient("openrouter", "m", api_key="")
        self.assertIn("OPENROUTER_API_KEY", str(ctx.exception))


class SummaryTest(unittest.TestCase):

    def test_runs_and_summaries_end_to_end(self):
        sample = drift.build_sample()
        right = "\n".join(f"{r['id']},{r['true_ratio']:.3f}" for r in sample)
        wrong = "\n".join(f"{r['id']},{r['true_ratio'] + 0.01:.3f}" for r in sample[:290])

        def respond(path, body):
            prompt = body["messages"][0]["content"]
            return {"choices": [{"message": {"content": right if "divide tool" in prompt else wrong}}],
                    "usage": {"prompt_tokens": 9000, "completion_tokens": 2500}}

        fake = FakeEndpoint(respond)
        self.addCleanup(fake.close)
        client = drift.ChatClient("openrouter", "test/model:1", base_url=fake.url, api_key="k", retries=0)
        with tempfile.TemporaryDirectory() as tmp, redirect_stdout(io.StringIO()):
            for setup in ("text", "tool"):
                drift.run_experiment(client, setup, runs=2, batch_size=300, max_turns=3, results_dir=tmp)
            self.assertTrue((Path(tmp) / "openrouter_test-model-1" / "tool" / "run_2.csv").exists())
            rows, by_setup = drift.summarize(tmp, usd_in=0.1, usd_out=0.4)
            self.assertEqual(len(rows), 4)
            text = next(s for s in by_setup if s["setup"] == "text")
            tool = next(s for s in by_setup if s["setup"] == "tool")
            self.assertEqual((text["exact_median"], text["dropped_or_duplicated_max"]), (0, 10))
            self.assertEqual((tool["exact_median"], tool["ids_where_runs_disagree"]), (300, 0))
            self.assertEqual(rows[0]["cost_usd"], 0.0019)
            svg = (Path(tmp) / "chart.svg").read_text(encoding="utf-8")
            self.assertIn("Exact compa-ratios out of 300", svg)
            self.assertNotIn("stroke", svg)
            self.assertFalse(any('"' in t for t in re.findall(r">([^<]+)<", svg)))
            self.assertTrue((Path(tmp) / "summary_by_setup.csv").exists())


if __name__ == "__main__":
    unittest.main()
