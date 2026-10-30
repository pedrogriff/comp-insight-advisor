"""Cross-lever policy questions: one filtered query per side, merged with labels for the writer.

The agent's own lever queries carry a lever filter, so a new-hire clause never answers a
question about a current employee's raise. A partner's question can still span levers, such
as "Compare the equity caps for new hires versus current staff". One unfiltered search mixes
the two populations, which is the trap checkpoint 3.1 describes, and one lever filter drops
half the answer. The checkpoint 3.1 graders suggested splitting such a question into one
filtered query per lever. This module does that in five steps:

1. Detect. `plan_question()` finds population words ("new hires", "current staff"), lever words
   ("raise", "promotion", "retention grant") and topic words both populations share ("equity",
   "salary", "compa-ratio"). A shared topic maps to the lever that governs it for each population:
   equity is an offer review for new hires and a retention grant for current employees. Each
   population and lever pair is one side. A question that names no population gets one side for
   each, so the population trap turns into two labeled answers.
2. Rewrite. Each side's query keeps its own topic words and drops the population words, which
   its filter now carries. When the question gives each side its own clause, such as "parental
   leave for new hires with retention grant tiers for current staff", each side keeps its own.
3. Search. `search_cross_lever()` runs each side with a strict filter on its population and its
   lever, under the normal relevance gate. The lever's playbook terms help rank the side's
   clauses but never count toward the gate, so a side the playbook doesn't cover stays empty.
   Clauses that apply to everyone (Sections 1 and 5, the Section 6 intro and table, and 6.5)
   form one shared group, searched once.
4. Merge. The writer gets one labeled group per side. A side with no clause says so, and a
   clause can sit under one population only.
5. Verify. `verify_comparison()` runs `verify_rule()` on each drafted claim and checks that its
   clause came from that side's group, so a new-hire limit can't be reported for current staff
   and an empty side can't borrow the other side's rule.

From the repo root:
    python3 -m src.retrieval.cross_lever "Compare the equity caps for new hires versus current staff"
    python3 -m src.retrieval.cross_lever --evaluate
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys
from typing import Any

from src.retrieval.embeddings import make_embedder
from src.retrieval.policy_search import ALL_LEVERS, CASES_PATH, LEVER_QUERIES, PolicyRetriever, verify_rule
from src.tools.interview_search import STOPWORDS

GRANT, BASE, LEVEL, BAND = ALL_LEVERS
NEW, CURRENT = "new_hires", "current_employees"
POPULATION_LEVERS = {NEW: [BAND], CURRENT: [GRANT, BASE, LEVEL]}
LEVER_POPULATION = {lever: pop for pop, levers in POPULATION_LEVERS.items() for lever in levers}
SHARED = ["all", "briefs"]  # applies_to of the clauses that govern every population
CROSS_CASES_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "synthetic" / "cross_lever_cases.json"

# Cue phrases come from the playbook's own terms, the tuning questions and the graders' message,
# never from the held-out questions. The longest phrase matches first and uses up its words.
POPULATION_CUES = {
    NEW: ["new hires", "new hire", "new-hires", "new-hire", "candidates", "candidate", "hiring"],
    CURRENT: ["current staff", "current employees", "current employee", "already on the team"],
}
LEVER_CUES = {
    GRANT: ["retention grants", "retention grant", "retention awards", "retention award", "retention money",
            "retention budget", "retention", "cliff bridge", "refresh", "tiers", "tier"],
    BASE: ["base adjustments", "base adjustment", "off-cycle", "pay increases", "pay increase", "raises", "raise",
           "lifts", "lift", "floor"],
    LEVEL: ["level reviews", "level review", "promotion reviews", "promotion review", "promotions", "promotion",
            "promoted", "moves up a level", "move up a level", "calibration"],
    BAND: ["offers desk", "offer bands", "offer band", "new-hire bands", "new-hire band", "sign-on"],
}
TOPIC_CUES = {
    "equity": ["equity", "stock", "rsus", "rsu", "grants", "grant", "awards", "award"],
    "pay": ["base salary", "salaries", "salary", "pay", "compa-ratio", "compa ratio", "market"],
    "level": ["levels", "level", "leveling", "titles", "title"],
}
TOPIC_LEVERS = {"equity": {NEW: BAND, CURRENT: GRANT}, "pay": {NEW: BAND, CURRENT: BASE},
                "level": {NEW: BAND, CURRENT: LEVEL}}
LEVER_TOPIC = {GRANT: "equity", BASE: "pay", LEVEL: "level"}
# Words that ask for a comparison instead of naming a topic. Rewritten side queries leave them out.
REWRITE_DROP = {"compare", "compared", "comparing", "comparison", "differ", "differs", "difference", "differences",
                "different", "versus", "vs", "same", "between"}
SPLIT_RE = re.compile(r"\b(?:versus|vs\.?|compared (?:with|to)|as opposed to|rather than|than|with|and|or)\b")
WORD_RE = re.compile(r"[a-z0-9]+(?:[-'][a-z0-9]+)*")
CUES = sorted([(p, "pop", key) for key, ps in POPULATION_CUES.items() for p in ps]
              + [(p, "lever", key) for key, ps in LEVER_CUES.items() for p in ps]
              + [(p, "topic", key) for key, ps in TOPIC_CUES.items() for p in ps], key=lambda c: -len(c[0]))
LABELS = {NEW: "New hires", CURRENT: "Current employees"}


# Detect and rewrite ------------------------------------------------------------------------
def _segment(text: str, offset: int = 0) -> dict[str, Any]:
    """Finds the cues in one clause of the question. Positions carry an offset per clause."""
    taken = [False] * len(text)
    seg: dict[str, Any] = {"pops": set(), "levers": {}, "topics": {}, "neutral": []}
    for phrase, kind, key in CUES:
        for m in re.finditer(r"(?<![\w-])" + re.escape(phrase) + r"(?![\w-])", text):
            if any(taken[m.start():m.end()]):
                continue
            taken[m.start():m.end()] = [True] * (m.end() - m.start())
            if kind == "pop":
                seg["pops"].add(key)
            else:
                seg["levers" if kind == "lever" else "topics"].setdefault(key, []).append((offset + m.start(), phrase))
    for m in WORD_RE.finditer(text):
        base = m.group(0).split("'")[0]
        if not any(taken[m.start():m.end()]) and base not in STOPWORDS and base not in REWRITE_DROP:
            seg["neutral"].append((offset + m.start(), m.group(0)))
    return seg


def _segments(question: str) -> list[dict[str, Any]]:
    text = question.lower().replace("\u2019", "'")
    segs: list[dict[str, Any]] = []
    for n, part in enumerate(SPLIT_RE.split(text)):
        seg = _segment(part, offset=10_000 * n)
        if segs and not seg["pops"] and not seg["levers"]:
            # Words with no population or lever of their own ("cash and equity") stay with the clause before.
            segs[-1]["neutral"] += seg["neutral"]
            for fam, found in seg["topics"].items():
                segs[-1]["topics"].setdefault(fam, []).extend(found)
        elif seg["pops"] or seg["levers"] or seg["topics"] or seg["neutral"]:
            segs.append(seg)
    for n, seg in enumerate(segs):
        if seg["levers"] or seg["topics"] or seg["neutral"]:
            continue
        # A clause that names only a population ("versus current staff") borrows the topic of the
        # nearest clause that has one. Lever words stay behind, and their topic comes along.
        for other in sorted((s for s in segs if s is not seg), key=lambda s: abs(segs.index(s) - n)):
            if other["topics"] or other["neutral"] or other["levers"]:
                seg["neutral"] = list(other["neutral"])
                seg["topics"] = {fam: list(found) for fam, found in other["topics"].items()}
                for lever in other["levers"]:
                    if lever in LEVER_TOPIC:
                        seg["topics"].setdefault(LEVER_TOPIC[lever], []).append((0, LEVER_TOPIC[lever]))
                break
    return segs


def plan_question(question: str) -> dict[str, Any]:
    """Splits a question into one side per population and lever it names, each with its own query."""
    segs = _segments(question)
    named = set().union(*(s["pops"] | {LEVER_POPULATION[lv] for lv in s["levers"]} for s in segs)) if segs else set()
    sides: dict[tuple[str, str | None], list[tuple[int, str]]] = {}
    for seg in segs:
        pops = seg["pops"] | {LEVER_POPULATION[lv] for lv in seg["levers"]} or named or {NEW, CURRENT}
        own: dict[tuple[str, str | None], list[tuple[int, str]]] = {}
        for lever, found in seg["levers"].items():
            own.setdefault((LEVER_POPULATION[lever], lever), []).extend(found)
        for fam, found in seg["topics"].items():
            for pop in sorted(pops):
                own.setdefault((pop, TOPIC_LEVERS[fam][pop]), []).extend(found)
        for pop in sorted(seg["pops"]):
            if not any(p == pop for p, _ in own):
                own[(pop, None)] = []
        for key, words in own.items():
            sides.setdefault(key, []).extend(words + seg["neutral"])
    order = sorted(sides, key=lambda k: (k[0] != NEW, ALL_LEVERS.index(k[1]) if k[1] else 9))
    planned = []
    for pop, lever in order:
        words = [w for _, w in sorted(set(sides[(pop, lever)]))]
        planned.append({"side": f"{pop}/{lever or 'any'}", "population": pop, "lever": lever,
                        "query": " ".join(dict.fromkeys(words)), "boost": LEVER_QUERIES.get(lever, "")})
    topic = [w for s in segs for _, w in sorted(set(s["neutral"] + [x for f in s["topics"].values() for x in f]
                                                  + [x for f in s["levers"].values() for x in f]))]
    route = "split" if len(planned) > 1 else "single" if planned else "open"
    if route == "single":
        # One side needs no rewrite: the question runs as asked, inside that side's filter.
        planned[0]["query"] = question
        return {"question": question, "route": route, "sides": planned, "shared_query": question}
    return {"question": question, "route": route, "sides": planned, "shared_query": " ".join(dict.fromkeys(topic))}


# Search and merge --------------------------------------------------------------------------
def _clause(hit: dict[str, Any]) -> dict[str, Any]:
    return {key: hit[key] for key in ("id", "heading", "text", "levers", "applies_to", "score")}


def search_cross_lever(retriever: PolicyRetriever, question: str, k: int = 3, shared_k: int = 1,
                       mode: str | None = None) -> dict[str, Any]:
    """Runs the plan: one strictly filtered search per side, one shared search, groups kept apart."""
    plan = plan_question(question)
    mode = mode or retriever.mode
    if plan["route"] == "open":
        hits = retriever.search(question, k=k, mode=mode)
        return {**plan, "groups": [], "shared": [], "open": [_clause(h) for h in hits]}
    groups = []
    for side in plan["sides"]:
        filters = {"applies_to": side["population"]}
        if side["lever"]:
            filters["levers"] = side["lever"]
        hits = retriever.search(side["query"], k=k, filters=filters, mode=mode, boost=side["boost"]) if side["query"] else []
        groups.append({**side, "clauses": [_clause(h) for h in hits], "status": "cited" if hits else "no_clause"})
    shared_query = plan["shared_query"]
    shared = retriever.search(shared_query, k=shared_k, filters={"applies_to": SHARED}, mode=mode) if shared_query else []
    return {**plan, "groups": groups, "shared": [_clause(h) for h in shared], "open": []}


def writer_context(result: dict[str, Any]) -> str:
    """The context block the writer model sees: every clause under its population and lever."""
    if result["route"] == "open":
        return "\n".join(f"[No population named] {c['id']}: {c['text']}" for c in result["open"]) or \
            "[No population named] No clause covers this question."
    lines = []
    for g in result["groups"]:
        label = f"{LABELS[g['population']]} | {g['lever'] or 'any lever'}"
        lines += [f"[{label}] {c['id']}: {c['text']}" for c in g["clauses"]] or [
            f"[{label}] No clause covers this side. Say so. Do not use another side's clause."]
    lines += [f"[Both populations] {c['id']}: {c['text']}" for c in result["shared"]]
    return "\n".join(lines)


def verify_comparison(result: dict[str, Any], claims: list[dict[str, Any]], retriever: PolicyRetriever) -> dict[str, Any]:
    """Checks a drafted comparison. Each claim is {"side", "text", "cited"}, with side as in the plan."""
    groups = {g["side"]: g for g in result["groups"]}
    shared = {c["id"] for c in result["shared"]}
    by_id = {c["id"]: c for c in retriever.chunks}
    problems: list[str] = []
    for claim in claims:
        group = groups.get(claim["side"])
        if group is None:
            problems.append(f"{claim['side']} is not a side of this question")
            continue
        ids = {c["id"] for c in group["clauses"]}
        if not ids:
            problems.append(f"No clause covers {claim['side']}, so the brief must say so instead of stating a rule")
            continue
        if claim.get("cited") and claim["cited"] not in ids | shared:
            problems.append(f"{claim['cited']} was not retrieved for {claim['side']}")
        lever = group["lever"]
        if lever is None:
            # A side that names a population but no lever checks against its only lever, or the cited clause's.
            levers, cited = POPULATION_LEVERS[group["population"]], by_id.get(claim.get("cited") or "")
            lever = levers[0] if len(levers) == 1 else (cited["levers"][0] if cited and cited["levers"] else None)
        if lever is None:
            problems.append(f"{claim['side']}: cite the clause the rule comes from")
            continue
        check = verify_rule(claim["text"], lever, retriever, claim.get("cited"))
        problems += [f"{claim['side']}: {p}" for p in check["problems"]]
    answered = {claim["side"] for claim in claims}
    missing = [g["side"] for g in result["groups"] if g["clauses"] and g["side"] not in answered]
    return {"ok": not problems and not missing, "problems": problems, "missing_sides": missing}


# Evaluation --------------------------------------------------------------------------------
def _side_ids(result: dict[str, Any], key: str) -> set[str]:
    pop, lever = key.split("/")
    return {c["id"] for g in result["groups"] if g["population"] == pop and (lever == "any" or g["lever"] in (lever, None))
            for c in g["clauses"]}


def _score_sides(case: dict[str, Any], found_for) -> dict[str, int]:
    out = {"sides": 0, "answered": 0, "empty_sides": 0, "kept_empty": 0, "all_sides": 1}
    for key, relevant in case["sides"].items():
        ids = found_for(key)
        if relevant:
            out["sides"] += 1
            out["answered"] += bool(ids & set(relevant))
            out["all_sides"] &= bool(ids & set(relevant))
        else:
            out["empty_sides"] += 1
            out["kept_empty"] += not ids
            out["all_sides"] &= not ids
    return out


def evaluate_cross_lever(retriever: PolicyRetriever, cases_path: Path = CROSS_CASES_PATH, split: str | None = "dev",
                         k: int = 3, mode: str | None = None) -> dict[str, Any]:
    """Compares one unfiltered query, one query with the first side's filter, and one query per side."""
    cases = [c for c in json.loads(Path(cases_path).read_text(encoding="utf-8")) if split is None or c["split"] == split]
    mode = mode or retriever.mode
    by_id = {c["id"]: c for c in retriever.chunks}
    configs = {name: {"sides": 0, "answered": 0, "empty_sides": 0, "kept_empty": 0, "all_sides": 0, "words": 0}
               for name in ("one query, no filter", "one query, first side's filter", "one query per side")}
    rows = []
    for case in cases:
        plan = plan_question(case["query"])
        open_hits = retriever.search(case["query"], k=k, mode=mode)
        first = plan["sides"][0] if plan["sides"] else None
        filters = ({"applies_to": first["population"], **({"levers": first["lever"]} if first["lever"] else {})}
                   if first else None)
        one_filter = retriever.search(case["query"], k=k, filters=filters, mode=mode) if first else open_hits
        split_result = search_cross_lever(retriever, case["query"], k=k, mode=mode)

        def by_population(hits):
            return lambda key: {h["id"] for h in hits if by_id[h["id"]]["applies_to"] == key.split("/")[0]}

        runs = {"one query, no filter": (by_population(open_hits), open_hits),
                "one query, first side's filter": (by_population(one_filter), one_filter),
                "one query per side": (lambda key: _side_ids(split_result, key),
                                       [c for g in split_result["groups"] for c in g["clauses"]] + split_result["shared"])}
        row = {"case_id": case["case_id"], "sides_planned": [g["side"] for g in split_result["groups"]]}
        for name, (found_for, hits) in runs.items():
            score = _score_sides(case, found_for)
            for key in ("sides", "answered", "empty_sides", "kept_empty", "all_sides"):
                configs[name][key] += score[key]
            configs[name]["words"] += sum(len(h["text"].split()) for h in hits)
            row[name] = score["all_sides"]
        rows.append(row)
    n = max(1, len(cases))
    report = {"split": split or "all", "questions": len(cases), "configs": {}, "cases": rows}
    for name, s in configs.items():
        report["configs"][name] = {"sides_answered": f"{s['answered']}/{s['sides']}",
                                   "empty_sides_kept_empty": f"{s['kept_empty']}/{s['empty_sides']}",
                                   "questions_fully_right": f"{s['all_sides']}/{len(cases)}",
                                   "mean_context_words": round(s["words"] / n)}
    return report


def evaluate_routing(retriever: PolicyRetriever, cases_path: Path = CASES_PATH, split: str | None = "dev",
                     k: int = 3, mode: str | None = None) -> dict[str, Any]:
    """Runs the 28 single-question cases through the router, so a split never costs a found clause."""
    cases = [c for c in json.loads(Path(cases_path).read_text(encoding="utf-8")) if split is None or c["split"] == split]
    mode = mode or retriever.mode
    out = {"split": split or "all", "routes": {"open": 0, "single": 0, "split": 0}, "one_query_hits": 0,
           "routed_hits": 0, "answerable": 0, "routed_abstained": 0, "no_answer": 0, "lost": [], "gained": []}
    for case in cases:
        result = search_cross_lever(retriever, case["query"], k=k, mode=mode)
        out["routes"][result["route"]] += 1
        routed = {c["id"] for g in result["groups"] for c in g["clauses"]} | {c["id"] for c in result["shared"] + result["open"]}
        single = {h["id"] for h in retriever.search(case["query"], k=k, mode=mode)}
        if case["relevant"]:
            out["answerable"] += 1
            hit_one, hit_routed = bool(single & set(case["relevant"])), bool(routed & set(case["relevant"]))
            out["one_query_hits"] += hit_one
            out["routed_hits"] += hit_routed
            if hit_one and not hit_routed:
                out["lost"].append(case["case_id"])
            if hit_routed and not hit_one:
                out["gained"].append(case["case_id"])
        else:
            out["no_answer"] += 1
            out["routed_abstained"] += not routed
    return out


def router_queries() -> list[str]:
    """Every query the router and its baselines send for the test questions, for `policy_search --save`."""
    questions = [c["query"] for path in (CASES_PATH, CROSS_CASES_PATH)
                 for c in json.loads(Path(path).read_text(encoding="utf-8"))]
    out = []
    for question in questions:
        plan = plan_question(question)
        out += [question] + [side["query"] for side in plan["sides"]] + [plan["shared_query"]]
    return list(dict.fromkeys(q for q in out if q))


def _print(result: dict[str, Any]) -> None:
    print(f"{result['question']}\nroute: {result['route']}")
    for g in result["groups"]:
        print(f"  {g['side']:<34} query \"{g['query']}\"")
    print(writer_context(result))


if __name__ == "__main__":
    args = sys.argv[1:]
    spec = args[args.index("--embedder") + 1] if "--embedder" in args and args.index("--embedder") + 1 < len(args) else None
    retriever = PolicyRetriever(make_embedder(spec))
    if "--evaluate" in args:
        missing = [q for q in router_queries() if getattr(retriever.embedder, "scores", None) is not None
                   and q not in retriever.embedder.scores]
        if missing:
            raise SystemExit(f"{len(missing)} router queries have no saved score, for example {missing[0]!r}. "
                             "Rerun policy_search --save with the model.")
        for split in ("dev", "heldout"):
            report = evaluate_cross_lever(retriever, split=split)
            print(f"\n{report['split']} cross-lever questions: {report['questions']}")
            for name, m in report["configs"].items():
                print(f"  {name:<32} sides {m['sides_answered']:>5}  empty kept {m['empty_sides_kept_empty']:>4}"
                      f"  fully right {m['questions_fully_right']:>5}  words {m['mean_context_words']:>4}")
            for row in report["cases"]:
                print(f"    {row['case_id']:<4} {', '.join(row['sides_planned'])}")
            routing = evaluate_routing(retriever, split=split)
            print(f"  routing the {routing['split']} single questions: {routing['routes']}, hits "
                  f"{routing['one_query_hits']} -> {routing['routed_hits']} of {routing['answerable']}, abstained "
                  f"{routing['routed_abstained']} of {routing['no_answer']}, lost {routing['lost']}, gained {routing['gained']}")
    else:
        words = [a for i, a in enumerate(args) if not a.startswith("--") and (i == 0 or args[i - 1] != "--embedder")]
        _print(search_cross_lever(retriever, " ".join(words) or "Compare the equity caps for new hires versus current staff"))
