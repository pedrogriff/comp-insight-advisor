"""Embedding backends for semantic retrieval. Standard library only.

    make_embedder("hashing")                        built in, no model. A lexical stand-in for tests
    make_embedder("ollama:nomic-embed-text")        a local model served by Ollama
    make_embedder("gemini:gemini-embedding-001")    Gemini's OpenAI-compatible endpoint, needs GEMINI_API_KEY
    make_embedder("openai:text-embedding-3-small")  OpenAI, needs OPENAI_API_KEY
    make_embedder("saved:scores.json")              replays scores saved by `policy_search --save`

Every backend returns L2-normalized vectors, so a dot product is the cosine similarity.
The hashing embedder hashes words and character trigrams into a fixed number of
dimensions. It matches "promoted" with "promotion" but not "underpaid" with "base
salary", so it is not a semantic model. The tests use it because it needs no network.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request

from src.tools.interview_search import tokenize

PROVIDERS = {
    # name: (default base URL, API key variable, wire format)
    "ollama": ("http://localhost:11434/", None, "ollama"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/", "GEMINI_API_KEY", "openai"),
    "openai": ("https://api.openai.com/v1/", "OPENAI_API_KEY", "openai"),
}
# Some models expect a task prefix on queries and documents (their model cards say so).
PREFIXES = {
    "nomic-embed-text": ("search_query: ", "search_document: "),
    "embeddinggemma": ("task: search result | query: ", "title: none | text: "),
}
# Abstain thresholds for the dense score. Tune them from `--evaluate` on the dev questions only.
# It prints the best score for every question, including the ones no clause answers.
# nomic-embed-text: set on Oct 24 from the run saved in experiments/policy_retrieval/. Its
# answerable dev questions scored at least 0.607 and its unanswerable ones at most 0.584.
# The other two are untuned starting points.
MIN_SIMILARITY = {"hashing": 0.30, "nomic-embed-text": 0.60, "embeddinggemma": 0.45}


def normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vector))
    return [v / norm for v in vector] if norm else list(vector)


def dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def texts_hash(texts: list[str]) -> str:
    return hashlib.sha256(json.dumps(texts).encode("utf-8")).hexdigest()


class HashingEmbedder:
    """Feature hashing of words and character trigrams. Deterministic across runs and machines."""

    def __init__(self, dim: int = 512) -> None:
        self.dim = dim
        self.name = f"hashing-{dim}"
        self.min_similarity = MIN_SIMILARITY["hashing"]

    def _features(self, text: str) -> dict[str, float]:
        feats: dict[str, float] = {}
        for token in tokenize(text):
            feats["w:" + token] = feats.get("w:" + token, 0.0) + 1.0
            padded = f"<{token}>"
            grams = [padded[i:i + 3] for i in range(len(padded) - 2)]
            for gram in grams:
                feats["c:" + gram] = feats.get("c:" + gram, 0.0) + 1.0 / len(grams)
        return feats

    def embed(self, texts: list[str], kind: str = "document") -> list[list[float]]:
        out = []
        for text in texts:
            vec = [0.0] * self.dim
            for feat, weight in self._features(text).items():
                h = int.from_bytes(hashlib.blake2b(feat.encode("utf-8"), digest_size=8).digest(), "little")
                vec[h % self.dim] += weight if (h >> 32) & 1 else -weight
            out.append(normalize(vec))
        return out


class HTTPEmbedder:
    """Calls Ollama's /api/embed or an OpenAI-compatible /embeddings endpoint in batches."""

    def __init__(self, provider: str, model: str, base_url: str | None = None, api_key: str | None = None,
                 timeout: float = 120.0, retries: int = 3, batch_size: int = 32) -> None:
        if provider not in PROVIDERS:
            raise ValueError(f"Unknown provider {provider!r}. Use one of {sorted(PROVIDERS)}.")
        default_url, key_var, self.wire = PROVIDERS[provider]
        self.provider, self.model = provider, model
        self.base_url = (base_url or default_url).rstrip("/") + "/"
        self.api_key = api_key if api_key is not None else (os.environ.get(key_var, "") if key_var else "")
        if key_var and not self.api_key:
            raise SystemExit(f"Set {key_var} first, for example: export {key_var}=...")
        self.timeout, self.retries, self.batch_size = timeout, retries, batch_size
        family = model.split(":")[0].split("/")[-1]
        self.query_prefix, self.document_prefix = PREFIXES.get(family, ("", ""))
        self.min_similarity = MIN_SIMILARITY.get(family)
        self.name = f"{provider}:{model}"
        host = urllib.parse.urlsplit(self.base_url).hostname
        # A local server, such as Ollama, is reached directly even when a proxy is configured.
        local = host in ("localhost", "127.0.0.1", "::1")
        self._open = urllib.request.build_opener(urllib.request.ProxyHandler({})).open if local else urllib.request.urlopen

    def _post(self, path: str, body: dict) -> dict:
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
                detail = exc.read().decode("utf-8", "replace")[:300]
                if exc.code in (429, 500, 502, 503, 504) and attempt < self.retries:
                    time.sleep(2 ** (attempt + 1))
                    continue
                raise RuntimeError(f"HTTP {exc.code} from {url}: {detail}") from None
            except (urllib.error.URLError, TimeoutError) as exc:
                if attempt < self.retries:
                    time.sleep(2 ** (attempt + 1))
                    continue
                raise RuntimeError(f"Can't reach {url}: {getattr(exc, 'reason', exc)}") from None
        raise RuntimeError(f"No response from {url}")

    def embed(self, texts: list[str], kind: str = "document") -> list[list[float]]:
        prefix = self.query_prefix if kind == "query" else self.document_prefix
        out: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = [prefix + t for t in texts[start:start + self.batch_size]]
            if self.wire == "ollama":
                vectors = self._post("api/embed", {"model": self.model, "input": batch})["embeddings"]
            else:
                rows = self._post("embeddings", {"model": self.model, "input": batch})["data"]
                vectors = [row["embedding"] for row in sorted(rows, key=lambda r: r.get("index", 0))]
            if len(vectors) != len(batch):
                raise RuntimeError(f"{self.name} returned {len(vectors)} vectors for {len(batch)} texts")
            out.extend(normalize([float(v) for v in vec]) for vec in vectors)
        return out


class SavedScoresEmbedder:
    """Replays the similarity scores that `policy_search --save` wrote, so a run with a real model
    can be reproduced and re-tuned without the model. Each clause becomes a basis vector and each
    saved query becomes its row of scores, so a dot product returns the saved score. Redundancy
    between clauses comes out as 0, so MMR needs real vectors."""

    def __init__(self, path: str | Path) -> None:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        self.name = "saved:" + data["embedder"]
        self.scores, self.texts_hash = data["scores"], data["texts_hash"]
        self.size = len(data["chunk_ids"])
        family = data["embedder"].split(":", 1)[-1].split(":")[0].split("/")[-1]
        # The code's threshold comes first, so a threshold tuned after the run applies to the replay.
        self.min_similarity = MIN_SIMILARITY.get(family, data.get("min_similarity"))

    def embed(self, texts: list[str], kind: str = "document") -> list[list[float]]:
        if kind == "query":
            missing = [t for t in texts if t not in self.scores]
            if missing:
                raise KeyError(f"No saved scores for {missing[0]!r}. Rerun --save with the model.")
            return [list(self.scores[t]) for t in texts]
        if len(texts) != self.size or texts_hash(texts) != self.texts_hash:
            raise ValueError("The playbook changed after these scores were saved. Rerun --save with the model.")
        return [[1.0 if j == i else 0.0 for j in range(self.size)] for i in range(self.size)]


def make_embedder(spec: str | None):
    """Builds an embedder from "hashing", "hashing:256", "saved:PATH" or "provider:model". None means none."""
    if not spec or spec == "none":
        return None
    if spec.startswith("saved:"):
        return SavedScoresEmbedder(spec[len("saved:"):])
    if spec == "hashing" or spec.startswith("hashing:"):
        return HashingEmbedder(int(spec.split(":", 1)[1]) if ":" in spec else 512)
    provider, _, model = spec.partition(":")
    if not model:
        raise ValueError(f"Embedder spec {spec!r} needs a model, for example ollama:nomic-embed-text")
    return HTTPEmbedder(provider, model)
