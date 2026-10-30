"""Hybrid search over short documents: BM25, dense vectors, or both fused by rank.

A document is a dict with "id", "text" and metadata fields. When "search_text" is present,
the scorers read it, and "text" stays the passage a brief quotes. Search runs in four steps:

1. Metadata filters narrow the pool, for example to clauses that govern one lever.
2. BM25, with the glossary expansion from src.tools.interview_search, ranks the pool, and a
   dense embedder ranks it by cosine similarity. Optional `boost` terms add to the BM25 score
   at half weight, so the cross-lever router can rank a side's clauses by its lever's terms.
3. A relevance gate keeps a document only if it matches at least half of the query's terms
   or its dense score clears the embedder's threshold. Boost terms don't count toward that
   half. When nothing passes, search returns an empty list, so the agent says no clause
   covers the question instead of quoting a near miss.
4. Reciprocal rank fusion merges the two rankings: score = sum of 1 / (60 + rank).

`load_or_build` keeps the vectors in a SQLite file with the embedder's name and a hash of the
corpus. A changed playbook or a different embedder rebuilds the index, so stale vectors never
answer a question about a policy that has changed.
"""

from __future__ import annotations

from array import array
from collections import Counter
from contextlib import closing
import hashlib
import json
import math
from pathlib import Path
import sqlite3
from typing import Any

from src.retrieval.embeddings import dot
from src.tools.interview_search import B, EXPANSION_WEIGHT, K1, _siblings, tokenize

RRF_K = 60
MODES = ("bm25", "dense", "hybrid")


def matches(doc: dict[str, Any], filters: dict[str, Any] | None) -> bool:
    """A list on either side means "any of". Everything else must be equal."""
    for key, want in (filters or {}).items():
        have = doc.get(key)
        wants = want if isinstance(want, (list, tuple, set)) else [want]
        haves = have if isinstance(have, (list, tuple, set)) else [have]
        if not any(w in haves for w in wants):
            return False
    return True


def corpus_hash(docs: list[dict[str, Any]]) -> str:
    rows = [[d["id"], d.get("search_text", d["text"])] for d in docs]
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode("utf-8")).hexdigest()


class HybridIndex:
    def __init__(self, docs: list[dict[str, Any]], embedder=None, vectors: list[list[float]] | None = None) -> None:
        self.docs, self.embedder = docs, embedder
        texts = [d.get("search_text", d["text"]) for d in docs]
        self.terms = [Counter(tokenize(t)) for t in texts]
        self.lengths = [sum(t.values()) for t in self.terms]
        self.avg_length = (sum(self.lengths) / len(self.lengths)) if docs else 0.0
        df: Counter[str] = Counter()
        for counts in self.terms:
            df.update(counts.keys())
        self.idf = {t: math.log(1 + (len(docs) - n + 0.5) / (n + 0.5)) for t, n in df.items()}
        if vectors is None and embedder is not None and docs:
            vectors = embedder.embed(texts, kind="document")
        self.vectors = vectors

    # Scoring -----------------------------------------------------------------
    def _bm25(self, i: int, weighted: dict[str, float]) -> float:
        counts, length, score = self.terms[i], self.lengths[i], 0.0
        for term, weight in weighted.items():
            tf = counts.get(term, 0)
            if tf:
                score += weight * self.idf.get(term, 0.0) * tf * (K1 + 1) / (
                    tf + K1 * (1 - B + B * length / self.avg_length))
        return score

    def _lexical(self, query: str, pool: list[int], expand: bool, boost: str = "") -> dict[int, tuple[float, float]]:
        terms = list(dict.fromkeys(tokenize(query)))
        if not terms:
            return {}
        weighted = {t: 1.0 for t in terms}
        if expand:
            for t in terms:
                for sib in _siblings(t):
                    weighted.setdefault(sib, EXPANSION_WEIGHT)
        # Boost terms help rank the pool at half weight but never count toward coverage, so they
        # can't lift a document past the relevance gate.
        for t in tokenize(boost):
            weighted.setdefault(t, EXPANSION_WEIGHT)
        out = {}
        for i in pool:
            present = self.terms[i]
            hit = [t for t in terms if t in present or (expand and any(s in present for s in _siblings(t)))]
            score = self._bm25(i, weighted)
            if score > 0:
                out[i] = (score, len(hit) / len(terms))
        return out

    def _similarity(self, a: int, b: int) -> float:
        if self.vectors is not None:
            return dot(self.vectors[a], self.vectors[b])
        ta, tb = self.terms[a], self.terms[b]
        num = sum(v * tb.get(t, 0) for t, v in ta.items())
        den = math.sqrt(sum(v * v for v in ta.values())) * math.sqrt(sum(v * v for v in tb.values()))
        return num / den if den else 0.0

    # Search ------------------------------------------------------------------
    def search(self, query: str, k: int = 3, mode: str = "hybrid", filters: dict[str, Any] | None = None,
               fetch_k: int = 20, expand: bool = True, min_coverage: float = 0.5,
               min_similarity: float | None = None, use_mmr: bool = False, lam: float = 0.5,
               boost: str = "") -> list[dict[str, Any]]:
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        if mode != "bm25" and self.vectors is None:
            raise ValueError("dense and hybrid search need an embedder")
        pool = [i for i, d in enumerate(self.docs) if matches(d, filters)]
        lexical = self._lexical(query, pool, expand, boost)
        dense: dict[int, float] = {}
        if mode != "bm25" and pool:
            qvec = self.embedder.embed([query], kind="query")[0]
            dense = {i: dot(qvec, self.vectors[i]) for i in pool}
        threshold = min_similarity if min_similarity is not None else getattr(self.embedder, "min_similarity", None)

        lex_rank = [i for i, (s, cov) in sorted(lexical.items(), key=lambda kv: (-kv[1][0], kv[0]))
                    if cov >= min_coverage][:fetch_k] if mode != "dense" else []
        den_rank = [i for i, s in sorted(dense.items(), key=lambda kv: (-kv[1], kv[0]))
                    if threshold is None or s >= threshold][:fetch_k] if mode != "bm25" else []
        fused: dict[int, float] = {}
        for ranking in (lex_rank, den_rank):
            for r, i in enumerate(ranking, start=1):
                fused[i] = fused.get(i, 0.0) + 1.0 / (RRF_K + r)
        order = sorted(fused, key=lambda i: (-fused[i], i))
        picked = self._mmr(order, fused, k, lam) if use_mmr else order[:k]
        hits = []
        for i in picked:
            doc = self.docs[i]
            hits.append({**{key: v for key, v in doc.items() if key != "search_text"},
                         "score": round(fused[i], 5),
                         "bm25": round(lexical.get(i, (0.0, 0.0))[0], 4),
                         "coverage": round(lexical.get(i, (0.0, 0.0))[1], 2),
                         "dense": round(dense[i], 4) if i in dense else None,
                         "bm25_rank": lex_rank.index(i) + 1 if i in lex_rank else None,
                         "dense_rank": den_rank.index(i) + 1 if i in den_rank else None})
        return hits

    def best_dense(self, query: str, filters: dict[str, Any] | None = None) -> float | None:
        """The highest dense score in the filtered pool, for tuning the abstain threshold."""
        if self.vectors is None:
            return None
        pool = [i for i, d in enumerate(self.docs) if matches(d, filters)]
        if not pool:
            return None
        qvec = self.embedder.embed([query], kind="query")[0]
        return round(max(dot(qvec, self.vectors[i]) for i in pool), 4)

    def _mmr(self, order: list[int], score: dict[int, float], k: int, lam: float) -> list[int]:
        """Min-max scales relevance to 0..1 first, as in Lab 3.2, so lam weighs the two terms evenly."""
        if not order:
            return []
        hi, lo = score[order[0]], min(score[i] for i in order)
        rel = {i: (score[i] - lo) / (hi - lo) if hi > lo else 1.0 for i in order}
        pool, chosen = list(order), []
        while pool and len(chosen) < k:
            def gain(i: int) -> float:
                redundancy = max((self._similarity(i, c) for c in chosen), default=0.0)
                return lam * rel[i] - (1 - lam) * redundancy
            best = max(pool, key=lambda i: (gain(i), -i))
            chosen.append(best)
            pool.remove(best)
        return chosen

    # Persistence -------------------------------------------------------------
    @classmethod
    def load_or_build(cls, path: str | Path, docs: list[dict[str, Any]], embedder) -> "HybridIndex":
        """Reuses stored vectors only when the embedder and the corpus hash both match."""
        digest, name = corpus_hash(docs), getattr(embedder, "name", "none")
        path = Path(path)
        if path.exists() and embedder is not None:
            with closing(sqlite3.connect(path)) as conn:
                meta = dict(conn.execute("SELECT key, value FROM index_meta").fetchall())
                if meta.get("corpus_hash") == digest and meta.get("embedder") == name:
                    rows = conn.execute("SELECT vector FROM docs ORDER BY position").fetchall()
                    vectors = [array("f", row[0]).tolist() for row in rows]
                    if len(vectors) == len(docs):
                        return cls(docs, embedder, vectors=vectors)
        index = cls(docs, embedder)
        if embedder is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(path)) as conn, conn:
                conn.execute("DROP TABLE IF EXISTS docs")
                conn.execute("DROP TABLE IF EXISTS index_meta")
                conn.execute("CREATE TABLE docs (id TEXT PRIMARY KEY, position INTEGER, doc TEXT, vector BLOB)")
                conn.execute("CREATE TABLE index_meta (key TEXT PRIMARY KEY, value TEXT)")
                conn.executemany("INSERT INTO docs VALUES (?, ?, ?, ?)", [
                    (d["id"], n, json.dumps(d), array("f", index.vectors[n]).tobytes()) for n, d in enumerate(docs)])
                conn.executemany("INSERT INTO index_meta VALUES (?, ?)", [
                    ("corpus_hash", digest), ("embedder", name), ("dimensions", str(len(index.vectors[0])))])
        return index
