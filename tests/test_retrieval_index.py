"""Unit tests for the embedders and the hybrid index. Standard library only, no network."""

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.retrieval.embeddings import HTTPEmbedder, HashingEmbedder, dot, make_embedder  # noqa: E402
from src.retrieval.hybrid_index import HybridIndex, matches  # noqa: E402


class FakeEmbeddingServer:
    """Answers /api/embed (Ollama) and /v1/embeddings (OpenAI wire) with fixed vectors."""

    def __init__(self):
        self.requests = []
        server = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                server.requests.append((self.path, body, self.headers.get("Authorization")))
                vectors = [[float(len(text)), 0.0, 1.0] for text in body["input"]]
                if self.path.endswith("/api/embed"):
                    reply = {"embeddings": vectors}
                else:
                    reply = {"data": [{"index": i, "embedding": v} for i, v in reversed(list(enumerate(vectors)))]}
                data = json.dumps(reply).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class CountingEmbedder(HashingEmbedder):
    def __init__(self, dim=64):
        super().__init__(dim)
        self.calls = 0

    def embed(self, texts, kind="document"):
        self.calls += 1
        return super().embed(texts, kind)


DOCS = [
    {"id": "a", "text": "Base salary floor at a 0.80 compa-ratio for current employees.", "levers": ["base"]},
    {"id": "b", "text": "New-hire offers up to a 1.00 compa-ratio need only desk approval.", "levers": ["offer"]},
    {"id": "c", "text": "The calibration committee decides promotions after a level review.", "levers": ["level"]},
    {"id": "d", "text": "Equity grants vest over four years on a front-loaded schedule.", "levers": []},
]


class EmbedderTest(unittest.TestCase):

    def test_hashing_is_deterministic_normalized_and_matches_word_forms(self):
        emb = HashingEmbedder(256)
        a, b, c = emb.embed(["promoted last cycle", "promotion this cycle", "vesting schedule"])
        self.assertEqual(emb.embed(["promoted last cycle"])[0], a)
        self.assertAlmostEqual(dot(a, a), 1.0, places=6)
        self.assertGreater(dot(a, b), dot(a, c))

    def test_make_embedder_parses_specs_without_network(self):
        self.assertIsNone(make_embedder(None))
        self.assertEqual(make_embedder("hashing:64").dim, 64)
        emb = make_embedder("ollama:nomic-embed-text")
        self.assertEqual((emb.name, emb.query_prefix, emb.min_similarity),
                         ("ollama:nomic-embed-text", "search_query: ", 0.55))
        with self.assertRaises(ValueError):
            make_embedder("ollama")
        with self.assertRaises(ValueError):
            make_embedder("acme:model")

    def test_ollama_wire_sends_prefixes_and_batches(self):
        fake = FakeEmbeddingServer()
        self.addCleanup(fake.close)
        emb = HTTPEmbedder("ollama", "nomic-embed-text", base_url=fake.url, retries=0, batch_size=2)
        vectors = emb.embed(["one", "two", "three"], kind="document")
        emb.embed(["q"], kind="query")
        self.assertEqual([r[0] for r in fake.requests], ["/api/embed"] * 3)
        self.assertEqual(fake.requests[0][1]["input"], ["search_document: one", "search_document: two"])
        self.assertEqual(fake.requests[2][1]["input"], ["search_query: q"])
        self.assertEqual(len(vectors), 3)
        self.assertAlmostEqual(dot(vectors[0], vectors[0]), 1.0, places=6)

    def test_openai_wire_sorts_by_index_and_sends_the_key(self):
        fake = FakeEmbeddingServer()
        self.addCleanup(fake.close)
        emb = HTTPEmbedder("openai", "text-embedding-3-small", base_url=fake.url + "v1/", api_key="k", retries=0)
        short, long = emb.embed(["ab", "abcdefgh"])
        path, body, auth = fake.requests[0]
        self.assertEqual((path, auth, body["model"]), ("/v1/embeddings", "Bearer k", "text-embedding-3-small"))
        self.assertGreater(long[0], short[0])


class HybridIndexTest(unittest.TestCase):

    def test_filters_accept_lists_on_either_side(self):
        self.assertTrue(matches({"levers": ["base", "level"]}, {"levers": "base"}))
        self.assertTrue(matches({"kind": "exit"}, {"kind": ["exit", "stay"]}))
        self.assertFalse(matches({"levers": ["offer"]}, {"levers": "base"}))

    def test_lever_filter_keeps_the_new_hire_rule_out(self):
        index = HybridIndex(DOCS)
        open_hits = [h["id"] for h in index.search("compa-ratio limit", k=2, mode="bm25")]
        base_hits = [h["id"] for h in index.search("compa-ratio limit", k=2, mode="bm25", filters={"levers": "base"})]
        self.assertIn("b", open_hits)
        self.assertEqual(base_hits, ["a"])

    def test_gate_returns_nothing_for_an_unanswered_question(self):
        index = HybridIndex(DOCS, HashingEmbedder(128))
        self.assertEqual(index.search("relocation allowance London", mode="bm25"), [])
        self.assertEqual(index.search("relocation allowance London", mode="hybrid", min_similarity=0.5), [])

    def test_hybrid_fuses_both_rankings(self):
        index = HybridIndex(DOCS, HashingEmbedder(128))
        hit = index.search("calibration committee promotion", k=1, mode="hybrid")[0]
        self.assertEqual(hit["id"], "c")
        self.assertEqual((hit["bm25_rank"], hit["dense_rank"]), (1, 1))
        self.assertAlmostEqual(hit["score"], round(2 / 61, 5))
        with self.assertRaises(ValueError):
            HybridIndex(DOCS).search("x", mode="dense")

    def test_index_file_is_reused_only_while_corpus_and_embedder_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "index.sqlite"
            emb = CountingEmbedder()
            first = HybridIndex.load_or_build(path, DOCS, emb)
            again = HybridIndex.load_or_build(path, DOCS, emb)
            self.assertEqual(emb.calls, 1)
            self.assertEqual([[round(v, 5) for v in vec] for vec in again.vectors],
                             [[round(v, 5) for v in vec] for vec in first.vectors])
            changed = [dict(DOCS[0], text="Base salary floor at a 0.85 compa-ratio.")] + DOCS[1:]
            HybridIndex.load_or_build(path, changed, emb)
            self.assertEqual(emb.calls, 2)
            other = CountingEmbedder(dim=32)
            HybridIndex.load_or_build(path, changed, other)
            self.assertEqual(other.calls, 1)


if __name__ == "__main__":
    unittest.main()
