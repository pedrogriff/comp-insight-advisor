"""Policy retrieval over the synthetic governance playbook.

Segmentation. `load_policy_chunks()` cuts the playbook into rules: one chunk per bullet or
numbered item, per paragraph, and one for the lever table, each tagged with its section, the
levers it governs and the population it applies to. Rules run 13 to 139 words and the lever
table 161, so a cited clause is exactly the passage a partner can check. `strategy="windows"`
cuts fixed word windows instead, for comparison in `--evaluate`.

Use in the agent. After the driver-fit check names the levers in play, the agent calls
`retrieve_for_lever()` for each one. The query names the lever and the loss drivers, and a
metadata filter keeps only clauses that govern that lever, so a new-hire offer rule never
answers a question about a current employee's raise. `check_limits()` then confirms that every
limit the code applies, such as the 0.95 lift ceiling, appears in a retrieved clause for that
lever. `verify_rule()` checks a drafted rule against the clause it cites.

From the repo root:
    python3 -m src.retrieval.policy_search "can we raise pay for underpaid scientists"
    python3 -m src.retrieval.policy_search --evaluate
    python3 -m src.retrieval.policy_search --evaluate --embedder ollama:nomic-embed-text \
        --save experiments/policy_retrieval/nomic-embed-text.json
    python3 -m src.retrieval.policy_search --evaluate --embedder saved:experiments/policy_retrieval/nomic-embed-text.json

`--save` writes the model's score for every question and agent query against every clause, so
the last command reproduces the run, and any change to the gate or the fusion can be scored
again, without the model.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys
from typing import Any

from src.retrieval.embeddings import dot, make_embedder, texts_hash
from src.retrieval.hybrid_index import HybridIndex
from src.tools.deterministic_analytics import TIER0_RATINGS
from src.tools.intervention_fit import POLICY

ROOT = Path(__file__).resolve().parent.parent.parent
PLAYBOOK_PATH = ROOT / "docs" / "policies" / "compensation_governance_playbook.md"
CASES_PATH = ROOT / "data" / "synthetic" / "policy_retrieval_cases.json"

ALL_LEVERS = ["retention_grant", "base_adjustment", "level_review", "offer_band_review"]
GRANT, BASE, LEVEL, BAND = ALL_LEVERS
# Section: (levers it governs, population it applies to). A section missing here is tagged
# "untagged", and a unit test fails, so a new playbook section can't hide from filtered queries.
SECTION_TAGS = {
    "1": ([], "all"), "2.1": ([BAND], "new_hires"), "2.2": ([GRANT], "current_employees"),
    "3": ([GRANT], "current_employees"), "4": ([GRANT, BASE, LEVEL], "current_employees"),
    "5": ([], "briefs"), "6": (ALL_LEVERS, "all"), "6.1": ([GRANT], "current_employees"),
    "6.2": ([BASE], "current_employees"), "6.3": ([LEVEL], "current_employees"),
    "6.4": ([BAND], "new_hires"), "6.5": (ALL_LEVERS, "briefs"),
}
LEVER_QUERIES = {
    "retention_grant": "proactive retention grant cliff bridge tier sizing equity refresh guideline",
    "base_adjustment": "off-cycle base salary adjustment compa-ratio floor lift eligibility funding sign-off",
    "level_review": "level review promotion candidates calibration committee decides cost",
    "offer_band_review": "new-hire offer bands thresholds Offers Desk review",
}
DRIVER_WORDS = {"Total_Equity_Size": "equity grant size", "Cashflow_Year1_Gap": "first-year cash gap",
                "Base_Salary_Cap": "base salary", "Level_Up_Offer": "level promotion"}
# The limits the code applies, written the way the playbook writes them.
TOOL_LIMITS = {
    "retention_grant": {"tier0_ratings": " or ".join(TIER0_RATINGS)},
    "base_adjustment": {"compa_floor": f"{POLICY['compa_floor']:.2f}",
                        "compa_lift_max": f"{POLICY['compa_lift_max']:.2f}"},
    "level_review": {"level_min_tenure_years": f"{POLICY['level_min_tenure_years']:g} years"},
}
NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
# Queries shown in checkpoint 3.1, and the cohorts whose agent queries --save records.
DEMO_QUERIES = ["Is there a compa-ratio cap for equity?", "What is the post-grant compa-ratio cap for retention grants?",
                "lowest pay relative to market for current staff"]
COHORTS = [("VP_CLOUD_AI", "RESEARCH_SCI"), ("VP_CLOUD_AI", "AI_ML_ENG"), ("VP_SEC_INTEL", "CYBER_SEC_ENG")]


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("**", "").replace("`", "").replace("*", "")).strip()


SLUG_SKIP = {"a", "an", "the", "to", "of", "and", "vs", "it", "what", "why", "per", "for"}


def _slug(lead: str) -> str:
    return "-".join([w for w in re.findall(r"[a-z0-9]+", lead.lower()) if w not in SLUG_SKIP][:2])


def _chunk(section: str, heading: str, intro: str, body: list[str], para: int, start: int, end: int) -> dict[str, Any]:
    raw = "\n".join(body).strip()
    first = re.sub(r"^(-|\d+\.)\s+", "", raw)
    lead = re.match(r"\*\*(.+?)\*\*", first)
    key = "table" if raw.startswith("|") else (_slug(lead.group(1)) if lead else f"p{para}")
    text = _clean(first if not raw.startswith("|") else raw)
    levers, applies_to = SECTION_TAGS.get(section, ([], "untagged"))
    return {"id": f"{section}:{key}", "section": section, "heading": heading, "text": text,
            "search_text": f"{heading}. {_clean(intro)} {text}".replace(" .", "."),
            "levers": list(levers), "applies_to": applies_to, "span": [start, end]}


def load_policy_chunks(path: Path = PLAYBOOK_PATH, strategy: str = "rules", window: int = 120,
                       overlap: int = 30) -> list[dict[str, Any]]:
    source = Path(path).read_text(encoding="utf-8")
    if strategy == "windows":
        return _windows(source, window, overlap)
    chunks: list[dict[str, Any]] = []
    section = heading = intro = ""
    body: list[str] = []
    start = pos = 0
    kind, gap = None, False

    def flush() -> None:
        nonlocal body, kind
        if body and section:
            paras = sum(1 for c in chunks if c["section"] == section and re.search(r":p\d+$", c["id"]))
            chunks.append(_chunk(section, heading, intro, body, paras + 1 if kind == "para" else 0, start, pos))
        body, kind = [], None

    for line in source.splitlines(keepends=True):
        text = line.rstrip("\n")
        top = re.match(r"^## Section (\d+)\. (.+)$", text)
        sub = re.match(r"^### (\d+\.\d+) (.+)$", text)
        if top or sub:
            flush()
            section = (top or sub).group(1)
            heading = f"Section {section}. {(top or sub).group(2)}" if top else f"Section {section} {sub.group(2)}"
            intro = ""
        elif not text.strip() or text.strip() == "---":
            gap = True
        elif text.startswith("|"):
            if kind != "table":
                flush()
                kind, start = "table", pos
            body.append(text)
        elif re.match(r"^(-|\d+\.) ", text):
            flush()
            kind, start = "item", pos
            body.append(text)
        elif text.startswith(" ") and kind == "item":
            body.append(text.strip())
        elif section:
            if text.rstrip().endswith(":"):
                flush()
                intro = text
            elif kind == "para" and not gap:
                body.append(text)
            else:
                flush()
                kind, start = "para", pos
                body.append(text)
        if text.strip():
            gap = False
        pos += len(line)
    flush()
    ids = [c["id"] for c in chunks]
    assert len(ids) == len(set(ids)), "duplicate chunk ids"
    return chunks


def _windows(source: str, window: int, overlap: int) -> list[dict[str, Any]]:
    words = [(m.start(), m.end()) for m in re.finditer(r"\S+", source)]
    out, step = [], max(1, window - overlap)
    for n, first in enumerate(range(0, max(1, len(words) - overlap), step)):
        span = words[first:first + window]
        start, end = span[0][0], span[-1][1]
        out.append({"id": f"w{n}", "section": "", "heading": "", "text": _clean(source[start:end]),
                    "levers": [], "applies_to": "", "span": [start, end]})
    return out


def lever_query(lever: str, drivers: list[str] | tuple[str, ...] = ()) -> str:
    """The agent's query for one lever, in playbook terms, built from the lever and the loss drivers."""
    return (LEVER_QUERIES[lever] + " " + " ".join(DRIVER_WORDS.get(d, d) for d in drivers)).strip()


def covers(window: dict[str, Any], rule: dict[str, Any], share: float = 0.5) -> bool:
    """A window covers a rule when it holds at least half of the rule's characters."""
    lo, hi = max(window["span"][0], rule["span"][0]), min(window["span"][1], rule["span"][1])
    return hi > lo and (hi - lo) >= share * (rule["span"][1] - rule["span"][0])


class PolicyRetriever:
    def __init__(self, embedder=None, path: Path = PLAYBOOK_PATH, strategy: str = "rules",
                 index_path: str | None = None) -> None:
        self.chunks = load_policy_chunks(path, strategy)
        self.embedder = embedder
        self.index = (HybridIndex.load_or_build(index_path, self.chunks, embedder) if index_path
                      else HybridIndex(self.chunks, embedder))
        self.mode = "hybrid" if embedder is not None else "bm25"

    def search(self, query: str, k: int = 3, filters: dict[str, Any] | None = None, **kw) -> list[dict[str, Any]]:
        # The interview-notes glossary maps "staff" to "level", which answers questions the playbook
        # doesn't cover, so policy search runs without it. See the held-out results in --evaluate.
        kw.setdefault("expand", False)
        return self.index.search(query, k=k, mode=kw.pop("mode", self.mode), filters=filters, **kw)

    def retrieve_for_lever(self, lever: str, drivers: list[str] | tuple[str, ...] = (), k: int = 3) -> list[dict[str, Any]]:
        return self.search(lever_query(lever, drivers), k=k, filters={"levers": lever}, min_coverage=0.0)

    def where(self, number: str) -> list[dict[str, Any]]:
        return [c for c in self.chunks if re.search(rf"(?<![\d.]){re.escape(number)}(?![\d])", c["text"])]


def check_limits(lever: str, clauses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Confirms that each limit the code applies for a lever appears in a retrieved clause for it."""
    out = []
    for name, value in TOOL_LIMITS.get(lever, {}).items():
        found = next((c["id"] for c in clauses if lever in c.get("levers", []) and value in c["text"]), None)
        out.append({"limit": name, "value": value, "found_in": found, "ok": found is not None})
    return out


def verify_rule(rule: str, lever: str, retriever: PolicyRetriever, cited: str | None = None) -> dict[str, Any]:
    """Checks a drafted rule: every number must appear in the cited clause, and the clause must govern the lever."""
    by_id = {c["id"]: c for c in retriever.chunks}
    problems = []
    clause = by_id.get(cited) if cited else None
    if cited and clause is None:
        problems.append(f"{cited} is not a clause in the playbook")
    if clause is not None and lever not in clause["levers"]:
        problems.append(f"{cited} governs {', '.join(clause['levers']) or 'no lever'}, not {lever}")
    for number in NUMBER_RE.findall(rule):
        if clause is not None and number in clause["text"]:
            continue
        homes = [c for c in retriever.where(number) if lever in c["levers"]]
        if homes and clause is None:
            continue
        others = [f"{c['id']} ({c['applies_to'].replace('_', ' ')})" for c in retriever.where(number)]
        problems.append(f"{number} does not appear in a {lever} clause" + (
            f". It appears in {', '.join(others)}" if others else ". It appears nowhere in the playbook"))
    return {"rule": rule, "lever": lever, "cited": cited, "ok": not problems, "problems": problems}


# Saved scores ------------------------------------------------------------------------------
def agent_queries(cohorts: list[tuple[str, str]] = COHORTS) -> list[str]:
    """Every policy query grounded_options sends for these cohorts."""
    from src.retrieval.grounded_options import CHECKLIST_QUERIES  # here, to avoid an import cycle
    from src.tools.intervention_fit import assess_intervention_fit
    out = [query for _, query in CHECKLIST_QUERIES.values()]
    for org, family in cohorts:
        drivers = [d for d, n in assess_intervention_fit(org, family)["departures"]["by_driver"].items() if n]
        out += [lever_query(lever, drivers) for lever in ALL_LEVERS]
    return list(dict.fromkeys(out))


def save_scores(embedder, out_path: str | Path, cases_path: Path = CASES_PATH,
                path: Path = PLAYBOOK_PATH) -> dict[str, Any]:
    """Writes the embedder's score for every test question and agent query against every clause."""
    chunks = load_policy_chunks(path)
    texts = [c["search_text"] for c in chunks]
    cases = json.loads(Path(cases_path).read_text(encoding="utf-8"))
    queries = list(dict.fromkeys([c["query"] for c in cases] + DEMO_QUERIES + agent_queries()))
    docs, vecs = embedder.embed(texts, kind="document"), embedder.embed(queries, kind="query")
    scores = {q: [round(dot(v, d), 5) for d in docs] for q, v in zip(queries, vecs)}
    head = {"embedder": embedder.name, "min_similarity": getattr(embedder, "min_similarity", None),
            "texts_hash": texts_hash(texts), "chunk_ids": [c["id"] for c in chunks]}
    lines = [json.dumps(head)[:-1] + ', "scores": {']
    lines += [f"  {json.dumps(q)}: {json.dumps(s)}" + ("," if n < len(scores) else "")
              for n, (q, s) in enumerate(scores.items(), start=1)]
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n}}\n", encoding="utf-8")
    return {**head, "scores": scores}


# Evaluation --------------------------------------------------------------------------------
def _configs(embedder) -> dict[str, dict[str, Any]]:
    configs = {"bm25 windows": {"strategy": "windows", "mode": "bm25", "expand": False},
               "bm25 rules": {"strategy": "rules", "mode": "bm25", "expand": False},
               "bm25 rules, floor 0.25": {"strategy": "rules", "mode": "bm25", "expand": False, "min_coverage": 0.25},
               "bm25 rules + glossary": {"strategy": "rules", "mode": "bm25", "expand": True}}
    if embedder is not None:
        configs[f"dense {embedder.name}"] = {"strategy": "rules", "mode": "dense", "expand": False}
        configs[f"hybrid {embedder.name}"] = {"strategy": "rules", "mode": "hybrid", "expand": False}
    return configs


def evaluate(embedder=None, cases_path: Path = CASES_PATH, k: int = 3, path: Path = PLAYBOOK_PATH,
             split: str | None = "dev") -> dict[str, Any]:
    """Scores each configuration on one split. Tune on "dev" and report "heldout", as Lab 3.2 advised."""
    cases = [c for c in json.loads(Path(cases_path).read_text(encoding="utf-8"))
             if split is None or c.get("split", "dev") == split]
    rules = {c["id"]: c for c in load_policy_chunks(path)}
    indexes = {s: HybridIndex(load_policy_chunks(path, s), embedder if s == "rules" else None)
               for s in ("rules", "windows")}
    report = {"k": k, "split": split or "all", "configs": {}, "cases": []}
    rows = {c["case_id"]: {"case_id": c["case_id"], "kind": c["kind"]} for c in cases}
    for name, cfg in _configs(embedder).items():
        index = indexes[cfg["strategy"]]
        stats = {"answerable": 0, "hit_at_1": 0, "hit_at_k": 0, "rr_sum": 0.0, "wrong_population_first": 0,
                 "no_answer": 0, "abstained_correctly": 0, "abstained_wrongly": 0, "context_words": 0}
        for case in cases:
            hits = index.search(case["query"], k=k, mode=cfg["mode"], expand=cfg["expand"],
                                min_coverage=cfg.get("min_coverage", 0.5))
            ids = [h["id"] for h in hits]
            stats["context_words"] += sum(len(h["text"].split()) for h in hits)
            if cfg["strategy"] == "windows":
                good = [any(covers(h, rules[r]) for r in case["relevant"]) for h in hits]
                wrong = [any(covers(h, rules[r]) for r in case.get("wrong_population", [])) for h in hits]
            else:
                good = [i in case["relevant"] for i in ids]
                wrong = [i in case.get("wrong_population", []) for i in ids]
            if case["relevant"]:
                stats["answerable"] += 1
                stats["abstained_wrongly"] += not hits
                stats["hit_at_1"] += bool(good[:1] and good[0])
                stats["hit_at_k"] += any(good)
                first = next((n for n, g in enumerate(good, 1) if g), None)
                stats["rr_sum"] += 1 / first if first else 0.0
                stats["wrong_population_first"] += bool(wrong and wrong[0])
            else:
                stats["no_answer"] += 1
                stats["abstained_correctly"] += not hits
            rows[case["case_id"]][name] = {"top": ids, "hit": any(good) if case["relevant"] else not hits}
        n = max(1, stats["answerable"])
        report["configs"][name] = {
            "hit_at_1": f"{stats['hit_at_1']}/{stats['answerable']}",
            f"hit_at_{k}": f"{stats['hit_at_k']}/{stats['answerable']}",
            "mrr": round(stats["rr_sum"] / n, 2),
            "wrong_population_first": stats["wrong_population_first"],
            "abstained_correctly": f"{stats['abstained_correctly']}/{stats['no_answer']}",
            "abstained_wrongly": stats["abstained_wrongly"],
            "mean_context_words": round(stats["context_words"] / max(1, len(cases))),
        }
    if embedder is not None:
        for case in cases:
            rows[case["case_id"]]["best_dense"] = indexes["rules"].best_dense(case["query"])
    report["cases"] = list(rows.values())
    return report


def _print_report(report: dict[str, Any]) -> None:
    k = report["k"]
    print(f"{report['split']} questions")
    print(f"{'config':<36} hit@1  hit@{k}  MRR   wrong-pop-first  abstain-ok  abstain-wrong  words")
    for name, m in report["configs"].items():
        print(f"{name:<36} {m['hit_at_1']:>5}  {m[f'hit_at_{k}']:>5}  {m['mrr']:<4}  {m['wrong_population_first']:>15}"
              f"  {m['abstained_correctly']:>10}  {m['abstained_wrongly']:>13}  {m['mean_context_words']:>5}")
    for row in report["cases"]:
        marks = " ".join(("+" if row[name]["hit"] else "-") for name in report["configs"])
        best = f"  best dense {row['best_dense']}" if row.get("best_dense") is not None else ""
        print(f"  {row['case_id']:<4} {row['kind']:<12} {marks}{best}")


def _option(args: list[str], name: str) -> str | None:
    return args[args.index(name) + 1] if name in args and args.index(name) + 1 < len(args) else None


if __name__ == "__main__":
    args = sys.argv[1:]
    embedder = make_embedder(_option(args, "--embedder"))
    if "--evaluate" in args:
        for split in ("dev", "heldout"):
            _print_report(evaluate(embedder, split=split))
    if "--save" in args:
        if embedder is None:
            raise SystemExit("--save needs --embedder, for example --embedder ollama:nomic-embed-text")
        saved = save_scores(embedder, _option(args, "--save"))
        print(f"saved {len(saved['scores'])} queries x {len(saved['chunk_ids'])} clauses to {_option(args, '--save')}")
    if "--evaluate" not in args and "--save" not in args:
        valued = {"--embedder", "--index"}
        words = [a for i, a in enumerate(args) if not a.startswith("--") and (i == 0 or args[i - 1] not in valued)]
        retriever = PolicyRetriever(embedder, index_path=_option(args, "--index"))
        for hit in retriever.search(" ".join(words) or "base salary floor"):
            print(f"{hit['id']:<28} score {hit['score']}  {hit['text'][:110]}")
