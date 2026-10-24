"""Generates synthetic exit and stay interview notes for retrieval practice.

Apex Cloud & AI Corp doesn't exist, and neither do these notes. The script reads
the synthetic database and writes two files next to it:

1. interview_notes.jsonl, one note per line:
   - EXIT notes, one for every lost counter-offer, meaning an employee who left.
     The note's main theme is that event's primary_loss_driver.
   - STAY notes, one for every counter-offer the employee accepted.
   - PSTAY notes, proactive stay interviews with every cliff-facing employee in
     the three hotspot job families. Their concerns follow transparent rules on
     roster fields, listed in _pstay_concerns, never the departure drivers.
2. interview_retrieval_cases.json, queries with the note IDs that answer them,
   labeled from note metadata so nobody has to judge relevance by hand.

The notes vary their wording on purpose. A keyword search for "salary" misses a
note that says "fixed pay", and several notes repeat one complaint almost word
for word, so retrieval tests can measure query expansion and diversity.

It has its own random seed and never touches the database, so every number in
the existing tables stays the same. Reruns write identical files.

Standard library only. Run from the repo root:
    python3 data/synthetic/generate_interview_notes.py
"""

from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
import random
import sqlite3

DATA_DIR = Path(__file__).resolve().parent
DB_PATH = DATA_DIR / "comp_insight_advisor.db"
NOTES_PATH = DATA_DIR / "interview_notes.jsonl"
CASES_PATH = DATA_DIR / "interview_retrieval_cases.json"
SEED = 20261022
HOTSPOTS = (("VP_CLOUD_AI", "RESEARCH_SCI"), ("VP_CLOUD_AI", "AI_ML_ENG"), ("VP_SEC_INTEL", "CYBER_SEC_ENG"))

DRIVER_SENTENCES = {
    "Base_Salary_Cap": [
        "My base salary had reached the top of the band, and {employer} offered a base about {premium} percent higher.",
        "The cash part of my pay was the problem. My fixed pay sat below what people at my level earn elsewhere.",
        "I asked twice for a raise and heard that the band would not move. The new role simply pays more.",
        "Base pay mattered most to me. The counter-offer added stock but left my salary where it was.",
    ],
    "Level_Up_Offer": [
        "{employer} offered me the next level up, with a senior title and a larger scope.",
        "I was passed over for promotion this cycle even though I led the project, and the new company hired me at staff level.",
        "I could not see a path to the next level here. The other offer came with a bigger title and a team to lead.",
        "The counter matched the money but not the role. I wanted the promotion, not more stock.",
    ],
    "Total_Equity_Size": [
        "The stock grant at {employer} was much larger than anything I would receive here over four years.",
        "Their RSU package was about {premium} percent bigger, and our counter closed only part of the gap.",
        "Equity decided it. The share award they offered dwarfed my refresh.",
    ],
    "Cashflow_Year1_Gap": [
        "My take-home pay next year was about to drop as my old grant finished vesting.",
        "{employer} offered a sign-on bonus that covered my first year, and our counter did not bridge that gap.",
        "If I had stayed, my first-year cash would have fallen sharply, because my vesting runs out in 2027.",
    ],
}
OTHER_SENTENCES = {
    "manager": ["My relationship with my manager had worn thin over the last year.",
                "I wanted a manager who would sponsor my work."],
    "commute": ["The move to the new office would have doubled my commute.",
                "I am relocating for family reasons."],
    "reorg": ["The reorg moved my project to another team."],
    "workload": ["The on-call load had become hard to sustain."],
    "remote_policy": ["The new return-to-office policy did not work for my family."],
}
STAY_REASONS = {
    "team": "I stay for my team. We work well together.",
    "mission": "I believe in what our group is building.",
    "manager": "My manager supports my growth and backs my ideas.",
    "flexibility": "The flexible schedule matters a lot to me.",
    "learning": "I am still learning quickly in this role.",
}
STAY_RISKS = {
    "Base_Salary_Cap": ["If my base salary stays flat, I would listen to outside offers.",
                        "My salary is below market for my level, and that wears on me."],
    "Level_Up_Offer": ["I need a clear path to the next level within a year.",
                       "If the promotion does not come this cycle, I would look elsewhere."],
    "Total_Equity_Size": ["A bigger stock grant somewhere else would tempt me.",
                          "My equity refresh looks small next to what recruiters quote."],
    "Cashflow_Year1_Gap": ["My cash flow drops next year when my grant ends, which worries me.",
                           "I am watching my 2027 take-home, because my vesting falls off then."],
}
CLOSINGS = ["Overall I enjoyed the work here.", "I would consider coming back later.", ""]


def _sentence(rng: random.Random, options: list[str], employer: str, premium: float) -> str:
    return rng.choice(options).format(employer=employer, premium=int(round(premium)))


def _exit_note(rng: random.Random, n: int, event: dict) -> dict:
    driver = event["primary_loss_driver"]
    themes = [driver]
    parts = [_sentence(rng, DRIVER_SENTENCES[driver], event["competing_employer"], event["competing_offer_premium_pct"])]
    if rng.random() < 0.4:
        second = rng.choice([d for d in DRIVER_SENTENCES if d != driver])
        themes.append(second)
        parts.append(_sentence(rng, DRIVER_SENTENCES[second], event["competing_employer"], event["competing_offer_premium_pct"]))
    if rng.random() < 0.35:
        other = rng.choice(sorted(OTHER_SENTENCES))
        themes.append(other)
        parts.append(rng.choice(OTHER_SENTENCES[other]))
    parts.append(rng.choice(CLOSINGS))
    return _note(f"EXIT-{n:04d}", "exit", event, themes, parts, source_event_id=event["event_id"])


def _stay_note(rng: random.Random, n: int, event: dict) -> dict:
    reason = rng.choice(sorted(STAY_REASONS))
    senior = event["job_level"] in ("IC3", "IC4")
    weights = [0.30, 0.35, 0.20, 0.15] if senior else [0.20, 0.20, 0.35, 0.25]
    risk = rng.choices(["Total_Equity_Size", "Level_Up_Offer", "Base_Salary_Cap", "Cashflow_Year1_Gap"], weights)[0]
    parts = [f"After the counter-offer I decided to stay. {STAY_REASONS[reason]}", rng.choice(STAY_RISKS[risk])]
    return _note(f"STAY-{n:04d}", "stay", event, [f"stay_{reason}", risk], parts, source_event_id=event["event_id"])


def _pstay_concerns(rng: random.Random, row: dict) -> list[str]:
    """Concern rules, each tied to a roster field. No rule reads departure drivers."""
    concerns = []
    if row["compa_ratio"] < 0.85 and rng.random() < 0.6:
        concerns.append("Base_Salary_Cap")
    if (row["rating_2025"] in ("rating_4", "rating_5") and row["tenure_years"] >= 2.0
            and row["job_level"] in ("IC2", "IC3", "IC4") and rng.random() < 0.5):
        concerns.append("Level_Up_Offer")
    if row["yoy_cashflow_change_26_to_27_pct"] <= -20.0 and rng.random() < 0.5:
        concerns.append("Cashflow_Year1_Gap")
    if not concerns or rng.random() < 0.15:
        concerns.append("Total_Equity_Size")
    return concerns[:2]


def _pstay_note(rng: random.Random, n: int, row: dict) -> dict:
    reason = rng.choice(sorted(STAY_REASONS))
    concerns = _pstay_concerns(rng, row)
    parts = [STAY_REASONS[reason]] + [rng.choice(STAY_RISKS[c]) for c in concerns]
    return _note(f"PSTAY-{n:04d}", "proactive_stay", row, [f"stay_{reason}"] + concerns, parts,
                 employee_id=row["employee_id"])


def _note(note_id: str, note_type: str, src: dict, themes: list[str], parts: list[str], **link: str) -> dict:
    return {
        "note_id": note_id, "note_type": note_type, **link,
        "vp_org_code": src["vp_org_code"], "job_family": src["job_family"], "job_level": src["job_level"],
        "region": src["region"], "quarter": src.get("quarter", "2026_Q4"),
        "themes": themes, "text": " ".join(p for p in parts if p),
    }


def _ids(notes: list[dict], **match: object) -> list[str]:
    out = []
    for note in notes:
        if all((note["themes"][0] == v) if k == "primary" else
               (v in note["themes"]) if k == "theme" else note.get(k) == v for k, v in match.items()):
            out.append(note["note_id"])
    return out


def build_cases(notes: list[dict]) -> list[dict]:
    """Queries labeled from note metadata. Each case says what it tests.

    The agent rewrites a partner's question into filters plus a short search query, the
    self-query step of retrieval. An empty search query means a metadata lookup.
    """
    rs = {"vp_org_code": "VP_CLOUD_AI", "job_family": "RESEARCH_SCI"}
    ai = {"vp_org_code": "VP_CLOUD_AI", "job_family": "AI_ML_ENG"}
    cyber = {"vp_org_code": "VP_SEC_INTEL", "job_family": "CYBER_SEC_ENG"}
    return [
        {"case_id": "R1", "question": "Why did research scientists leave after we made a counter-offer?",
         "search_query": "", "filters": {**rs, "note_type": "exit"},
         "relevant": _ids(notes, note_type="exit", **rs),
         "tests": "A metadata lookup returns every exit note for the cohort, with no text match needed."},
        {"case_id": "R2", "question": "Did people who left mention promotion or title?",
         "search_query": "promotion title", "filters": {"note_type": "exit"},
         "relevant": _ids(notes, note_type="exit", theme="Level_Up_Offer"),
         "tests": "Notes also say staff level, next level, senior or path, so expansion should raise recall."},
        {"case_id": "R3", "question": "Who says their base salary is below market?",
         "search_query": "base salary below market", "filters": {},
         "relevant": _ids(notes, theme="Base_Salary_Cap"),
         "tests": "Some notes say fixed pay, raise or band instead of salary."},
        {"case_id": "R4", "question": "Who mentions a first-year cash gap or a sign-on bonus?",
         "search_query": "first year cash gap sign-on bonus", "filters": {},
         "relevant": _ids(notes, theme="Cashflow_Year1_Gap"),
         "tests": "Paraphrases such as take-home pay and vesting runs out."},
        {"case_id": "R5", "question": "Which departures blame a small stock grant next to the competitor's?",
         "search_query": "stock grant competitor", "filters": {"note_type": "exit"},
         "relevant": _ids(notes, note_type="exit", theme="Total_Equity_Size"),
         "tests": "RSU package and share award are equity too, so expansion should raise recall."},
        {"case_id": "R6", "question": "What keeps cyber security engineers from leaving?",
         "search_query": "", "filters": {**cyber, "note_type": "proactive_stay"},
         "relevant": _ids(notes, note_type="proactive_stay", **cyber),
         "tests": "A metadata lookup over 48 stay interviews. MMR should show more distinct themes than the first five by ID."},
        {"case_id": "R7", "question": "Which concerns come up in stay interviews with cliff-facing research scientists?",
         "search_query": "salary promotion stock cash concerns",
         "sub_queries": ["salary", "promotion", "stock", "cash"], "filters": {**rs, "note_type": "proactive_stay"},
         "relevant": _ids(notes, note_type="proactive_stay", **rs),
         "tests": "A mixed question split into four sub-queries. As one query it fails the coverage floor, "
                  "because each note names only one or two concerns."},
        {"case_id": "R8", "question": "Did anyone leave over problems with their manager?",
         "search_query": "manager problems", "filters": {},
         "relevant": _ids(notes, theme="manager"),
         "tests": "Precision on a non-pay theme that shares the word manager with stay notes about supportive managers."},
        {"case_id": "R9", "question": "Any complaints about the parental leave policy?",
         "search_query": "parental leave policy complaints", "filters": {},
         "relevant": [],
         "tests": "No note covers this, so the search should return nothing."},
        {"case_id": "R10", "question": "Did AI/ML engineers who left cite equity?",
         "search_query": "stock equity grant", "filters": {**ai, "note_type": "exit"},
         "relevant": _ids(notes, note_type="exit", theme="Total_Equity_Size", **ai),
         "tests": "Filters plus expansion inside one cohort."},
    ]


def generate(db_path: Path = DB_PATH, notes_path: Path = NOTES_PATH, cases_path: Path = CASES_PATH) -> list[dict]:
    rng = random.Random(SEED)
    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        events = [dict(r) for r in conn.execute(
            "SELECT * FROM reactive_offers_counters WHERE event_type = 'Reactive_Counter_Offer' ORDER BY event_id")]
        roster = [dict(r) for r in conn.execute(
            "SELECT * FROM org_roster_cashflows WHERE yoy_cashflow_change_26_to_27_pct <= -15.0 ORDER BY employee_id")]
    notes: list[dict] = []
    for event in events:
        if event["outcome"] == "Declined_Lost":
            notes.append(_exit_note(rng, len([n for n in notes if n["note_type"] == "exit"]) + 1, event))
        else:
            notes.append(_stay_note(rng, len([n for n in notes if n["note_type"] == "stay"]) + 1, event))
    count = 0
    for row in roster:
        if (row["vp_org_code"], row["job_family"]) in HOTSPOTS:
            count += 1
            notes.append(_pstay_note(rng, count, row))
    notes_path.write_text("".join(json.dumps(n, sort_keys=True) + "\n" for n in notes), encoding="utf-8")
    cases_path.write_text(json.dumps(build_cases(notes), indent=2) + "\n", encoding="utf-8")
    return notes


if __name__ == "__main__":
    written = generate()
    by_type: dict[str, int] = {}
    for note in written:
        by_type[note["note_type"]] = by_type.get(note["note_type"], 0) + 1
    print(f"Wrote {len(written)} notes to {NOTES_PATH.name}: {by_type}, and {CASES_PATH.name}")
