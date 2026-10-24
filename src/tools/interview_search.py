"""Searches the synthetic exit and stay interview notes.

A lexical retrieval baseline for Module 3, standard library only:

1. Metadata filters narrow the pool first, for example to one cohort's exit notes.
2. BM25 scores each note against the query.
3. Query expansion adds sibling terms from a small compensation glossary, so a
   search for "salary" also finds "fixed pay" and "raise".
4. A coverage floor drops notes that match less than half of the query's
   meaning, so a question no note answers returns nothing.
5. A question with several parts runs as one sub-query per part, and the
   results merge, so each part gets its own chance to match.
6. Maximal marginal relevance (MMR) re-ranks the candidates so near-duplicate
   notes don't fill the top results. With lam = 0.5 it weighs relevance and
   novelty equally.

Embedding search can replace the BM25 scorer later. The filters, the floor, MMR
and the evaluation cases in data/synthetic/interview_retrieval_cases.json stay.

Run the evaluation from the repo root:
    python3 -m src.tools.interview_search --evaluate
"""

from __future__ import annotations

from collections import Counter
import json
import math
from pathlib import Path
import re
import sys
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "synthetic"
NOTES_PATH = DATA_DIR / "interview_notes.jsonl"
CASES_PATH = DATA_DIR / "interview_retrieval_cases.json"

STOPWORDS = set(
    "a an and are as at be because but by did do does for from had has have he her his how i if in into is it "
    "its me more most my not of on or our over so that the their them then there they this to too up was we "
    "were what when where which while who why will with would you your after about".split()
)
# Sibling terms a partner might use for the same idea. Expansion adds them at half weight.
GLOSSARY = [
    {"salary", "base", "pay", "raise", "band", "fixed", "paycheck"},
    {"promotion", "promoted", "title", "level", "staff", "senior", "scope", "path", "ladder"},
    {"equity", "stock", "rsu", "share", "grant", "award", "refresh"},
    {"cash", "cashflow", "take", "home", "sign", "bonus", "vesting", "first"},
    {"manager", "sponsor", "boss"},
]
EXPANSION_WEIGHT = 0.5
K1, B = 1.5, 0.75
DEFAULT_MIN_COVERAGE = 0.5


def tokenize(text: str) -> list[str]:
    tokens = []
    for raw in re.findall(r"[a-z0-9]+", text.lower()):
        if raw in STOPWORDS:
            continue
        if len(raw) > 4 and raw.endswith("ies"):
            raw = raw[:-3] + "y"
        elif len(raw) > 3 and raw.endswith("s") and not raw.endswith("ss"):
            raw = raw[:-1]
        tokens.append(raw)
    return tokens


def _siblings(term: str) -> set[str]:
    return set().union(*(group for group in GLOSSARY if term in group)) - {term}


def load_notes(path: Path = NOTES_PATH) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


class NoteIndex:
    """BM25 over the notes, with per-note term counts kept for coverage and MMR."""

    def __init__(self, notes: list[dict[str, Any]]) -> None:
        self.notes = notes
        self.terms = [Counter(tokenize(n["text"])) for n in notes]
        self.lengths = [sum(t.values()) for t in self.terms]
        self.avg_length = (sum(self.lengths) / len(self.lengths)) if notes else 0.0
        doc_freq: Counter[str] = Counter()
        for counts in self.terms:
            doc_freq.update(counts.keys())
        n = len(notes)
        self.idf = {t: math.log(1 + (n - df + 0.5) / (df + 0.5)) for t, df in doc_freq.items()}

    def _bm25(self, i: int, weighted: dict[str, float]) -> float:
        counts, length, score = self.terms[i], self.lengths[i], 0.0
        for term, weight in weighted.items():
            tf = counts.get(term, 0)
            if tf:
                norm = tf * (K1 + 1) / (tf + K1 * (1 - B + B * length / self.avg_length))
                score += weight * self.idf.get(term, 0.0) * norm
        return score

    def search(self, query: str, k: int = 5, filters: dict[str, Any] | None = None, expand: bool = True,
               use_mmr: bool = False, lam: float = 0.5, fetch_k: int = 20,
               min_coverage: float = DEFAULT_MIN_COVERAGE) -> list[dict[str, Any]]:
        query_terms = list(dict.fromkeys(tokenize(query)))
        if not query_terms:
            if not filters:
                return []
            # A metadata lookup: every filtered note is equally relevant, in note ID order.
            pool = sorted((1.0, 1.0, i) for i, n in enumerate(self.notes)
                          if all(n.get(key) == value for key, value in filters.items()))
            pool.sort(key=lambda item: self.notes[item[2]]["note_id"])
            picked = self._mmr(pool[:fetch_k], k, lam) if use_mmr else pool[:k]
            return [self._hit(score, cov, i) for score, cov, i in picked]
        weighted = {t: 1.0 for t in query_terms}
        if expand:
            for term in query_terms:
                for sib in _siblings(term):
                    weighted.setdefault(sib, EXPANSION_WEIGHT)
        scored = []
        for i, note in enumerate(self.notes):
            if filters and any(note.get(key) != value for key, value in filters.items()):
                continue
            present = self.terms[i]
            matched = [t for t in query_terms
                       if t in present or (expand and any(s in present for s in _siblings(t)))]
            coverage = len(matched) / len(query_terms)
            if coverage < min_coverage:
                continue
            score = self._bm25(i, weighted)
            if score > 0:
                scored.append((score, coverage, i))
        scored.sort(key=lambda item: (-item[0], self.notes[item[2]]["note_id"]))
        picked = self._mmr(scored[:fetch_k], k, lam) if use_mmr else scored[:k]
        return [self._hit(score, cov, i) for score, cov, i in picked]

    def search_many(self, sub_queries: list[str], k: int = 5, filters: dict[str, Any] | None = None,
                    expand: bool = True, use_mmr: bool = False, lam: float = 0.5,
                    fetch_k: int = 20) -> list[dict[str, Any]]:
        """Runs one search per part of a mixed question and merges the results.

        Each part's scores are divided by that part's best score, so a part with rare
        words cannot crowd out the others. A note found by several parts keeps its best score.
        """
        best: dict[int, tuple[float, float]] = {}
        id_to_index = {n["note_id"]: i for i, n in enumerate(self.notes)}
        for sub in sub_queries:
            hits = self.search(sub, k=fetch_k, filters=filters, expand=expand, fetch_k=fetch_k)
            top = hits[0]["score"] if hits else 0.0
            for hit in hits:
                i = id_to_index[hit["note_id"]]
                rel = hit["score"] / top if top else 0.0
                if rel > best.get(i, (-1.0, 0.0))[0]:
                    best[i] = (rel, hit["coverage"])
        merged = sorted(((rel, cov, i) for i, (rel, cov) in best.items()),
                        key=lambda item: (-item[0], self.notes[item[2]]["note_id"]))
        picked = self._mmr(merged[:fetch_k * 2], k, lam) if use_mmr else merged[:k]
        return [self._hit(score, cov, i) for score, cov, i in picked]

    def near_duplicates(self, note_ids: list[str], threshold: float = 0.8) -> int:
        """Counts results whose wording nearly repeats an earlier result."""
        index = {n["note_id"]: i for i, n in enumerate(self.notes)}
        ids = [index[n] for n in note_ids]
        return sum(1 for j in range(1, len(ids))
                   if max(self._cosine(ids[j], ids[m]) for m in range(j)) >= threshold)

    def _hit(self, score: float, coverage: float, i: int) -> dict[str, Any]:
        note = self.notes[i]
        return {"note_id": note["note_id"], "score": round(score, 4), "coverage": round(coverage, 2),
                "note_type": note["note_type"], "themes": note["themes"], "text": note["text"]}

    def _cosine(self, a: int, b: int) -> float:
        ta, tb = self.terms[a], self.terms[b]
        dot = sum(v * tb.get(t, 0) for t, v in ta.items())
        norm = math.sqrt(sum(v * v for v in ta.values())) * math.sqrt(sum(v * v for v in tb.values()))
        return dot / norm if norm else 0.0

    def _mmr(self, candidates: list[tuple[float, float, int]], k: int, lam: float) -> list[tuple[float, float, int]]:
        if not candidates:
            return []
        top = candidates[0][0]
        pool, chosen = list(candidates), []
        while pool and len(chosen) < k:
            def gain(item: tuple[float, float, int]) -> float:
                redundancy = max((self._cosine(item[2], c[2]) for c in chosen), default=0.0)
                return lam * item[0] / top - (1 - lam) * redundancy
            best = max(pool, key=lambda item: (gain(item), -item[2]))
            chosen.append(best)
            pool.remove(best)
        return chosen


CONFIGS = {
    "plain": {"expand": False, "use_mmr": False},
    "expanded": {"expand": True, "use_mmr": False},
    "expanded_mmr": {"expand": True, "use_mmr": True},
}


def _themes(results: list[dict[str, Any]]) -> int:
    return len({t for r in results for t in r["themes"]})


def evaluate(notes_path: Path = NOTES_PATH, cases_path: Path = CASES_PATH, k: int = 5) -> dict[str, Any]:
    """Runs every case under each configuration and reports precision, recall and diversity."""
    index = NoteIndex(load_notes(notes_path))
    cases = json.loads(Path(cases_path).read_text(encoding="utf-8"))
    rows = []
    for case in cases:
        relevant = set(case["relevant"])
        row = {"case_id": case["case_id"], "relevant": len(relevant), "tests": case["tests"]}
        for name, config in CONFIGS.items():
            filters = case["filters"] or None
            if case.get("sub_queries"):
                results = index.search_many(case["sub_queries"], k=k, filters=filters, **config)
                wide = index.search_many(case["sub_queries"], k=10, filters=filters, **config)
            else:
                results = index.search(case["search_query"], k=k, filters=filters, **config)
                wide = index.search(case["search_query"], k=10, filters=filters, **config)
            hits = sum(r["note_id"] in relevant for r in results)
            row[name] = {
                "returned": len(results),
                "precision_at_k": round(hits / len(results), 2) if results else None,
                "recall_at_10": (round(sum(r["note_id"] in relevant for r in wide) / len(relevant), 2)
                                 if relevant and len(relevant) <= 15 else None),
                "distinct_themes_at_k": _themes(results),
                "near_duplicates_at_k": index.near_duplicates([r["note_id"] for r in results]),
                "abstained": not results,
            }
        rows.append(row)
    summary = {}
    for name in CONFIGS:
        scored = [r[name]["precision_at_k"] for r in rows if r["relevant"] and r[name]["precision_at_k"] is not None]
        summary[name] = {
            "mean_precision_at_k": round(sum(scored) / len(scored), 2) if scored else None,
            "answered_cases": sum(1 for r in rows if r["relevant"] and r[name]["returned"]),
            "abstained_correctly": sum(1 for r in rows if not r["relevant"] and r[name]["abstained"]),
        }
    return {"k": k, "cases": rows, "summary": summary}


def _print_report(report: dict[str, Any]) -> None:
    print(f"case  relevant | {' | '.join(f'{n}: P@{report['k']} R@10 themes dups' for n in CONFIGS)}")
    for row in report["cases"]:
        cells = []
        for name in CONFIGS:
            m = row[name]
            cells.append(f"{m['precision_at_k'] if m['precision_at_k'] is not None else '-':>4} "
                         f"{m['recall_at_10'] if m['recall_at_10'] is not None else '-':>4} "
                         f"{m['distinct_themes_at_k']:>2} {m['near_duplicates_at_k']:>2}"
                         + (" (none)" if m["abstained"] else ""))
        print(f"{row['case_id']:<5} {row['relevant']:>8} | " + " | ".join(cells))
    print("summary:", json.dumps(report["summary"]))


if __name__ == "__main__":
    if "--evaluate" in sys.argv[1:]:
        _print_report(evaluate())
    else:
        query = " ".join(a for a in sys.argv[1:] if not a.startswith("--")) or "why did people leave"
        for hit in NoteIndex(load_notes()).search(query, use_mmr=True):
            print(hit["note_id"], hit["score"], hit["text"])
