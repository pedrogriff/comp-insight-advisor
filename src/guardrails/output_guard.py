"""Output checks that run after the figure verifier and before any release.

deterministic_verify_brief() in src/agents/state.py already traces every
currency figure, percentage, coverage ratio, clause ID, sign-off and
disclosure to a tool output. check_brief() adds the checks that concern what
a brief may say at all:

- employee_identifier: a brief is cohort level, so it never carries an
  employee ID or an offer event ID.
- decision_claim: the advisor prepares analysis and a person decides, so a
  brief never says that something was approved, granted or paid.
- headcount_mismatch: the cliff count, headcount and manager inversion count
  a brief states must equal the roster scan's numbers.
- unsupported_certainty: a brief never promises an outcome, because the
  tools measure exposure and cost, not what a person will do.
"""

from __future__ import annotations

import re

from src.agents.state import SquadState

EMPLOYEE_ID_RE = re.compile(r"\b(EMP\d{4,6}|OFFER\d{6,8})\b")
DECISION_CLAIM_RE = re.compile(
    r"\b(has|have|had|was|were|is|are|been)\s+(now\s+|already\s+|been\s+)*(approved|granted|awarded|authorized|"
    r"issued|paid out|signed off|finalized)\b|\b(we|i)\s+(approve|approved|grant|granted|authorize|authorized|"
    r"have approved|have granted)\b|\bapproved by\b",
    re.I,
)
CERTAINTY_RE = re.compile(
    r"\b(guarantee[sd]?|will (certainly|definitely) (stay|retain|accept)|will not leave|won't leave|"
    r"ensures? (retention|they stay)|eliminates? (attrition|the risk)|zero risk|risk[- ]free|"
    r"100% (certain|sure|retention))\b",
    re.I,
)
CLIFF_CLAIM_RE = re.compile(r"\b([0-9][0-9,]*)\s+cliff cases across\s+([0-9][0-9,]*)\s+employees\b", re.I)
INVERSION_CLAIM_RE = re.compile(r"\b([0-9][0-9,]*)\s+manager inversions?\b", re.I)


def brief_text(state: SquadState) -> str:
    """Every field of the draft that reaches a reader, as one string."""
    draft = state.draft
    if draft is None:
        return ""
    parts = [draft.headline, draft.summary, *draft.option_lines, *draft.uncertainty_disclosures, *draft.memory_notes]
    parts += [claim.text for claim in draft.claims]
    return "\n".join(parts)


def check_text(text: str, org_summary: dict | None = None) -> tuple[str, ...]:
    """Checks one block of brief text. org_summary is the roster scan's org_summary dict."""
    issues: list[str] = []
    for hit in dict.fromkeys(EMPLOYEE_ID_RE.findall(text)):
        issues.append(f"employee_identifier: the brief names {hit}, and briefs stay at cohort level")
    claim = DECISION_CLAIM_RE.search(text)
    if claim:
        issues.append(f"decision_claim: '{claim.group(0)}' states a decision, and only a person decides")
    promise = CERTAINTY_RE.search(text)
    if promise:
        issues.append(f"unsupported_certainty: '{promise.group(0)}' promises an outcome no tool measures")
    if org_summary:
        for hit in CLIFF_CLAIM_RE.finditer(text):
            stated = (int(hit.group(1).replace(",", "")), int(hit.group(2).replace(",", "")))
            actual = (int(org_summary["cliff_count_gt_15pct"]), int(org_summary["total_headcount"]))
            if stated != actual:
                issues.append(
                    f"headcount_mismatch: the brief says {stated[0]} cliff cases across {stated[1]} employees, "
                    f"the roster scan says {actual[0]} across {actual[1]}"
                )
        for hit in INVERSION_CLAIM_RE.finditer(text):
            stated_inv = int(hit.group(1).replace(",", ""))
            if stated_inv != int(org_summary["manager_inversion_count"]):
                issues.append(
                    f"headcount_mismatch: the brief says {stated_inv} manager inversions, the roster scan says "
                    f"{org_summary['manager_inversion_count']}"
                )
    return tuple(issues)


def org_summary_from(state: SquadState) -> dict | None:
    for finding in state.findings:
        if finding.kind == "org_cliff_health":
            return finding.payload.get("org_summary")
    return None


def _retrieved_clause_texts(state: SquadState) -> list[str]:
    texts: list[str] = []
    for grounded in state.grounded_by_cohort.values():
        for hits in grounded.get("clauses", {}).values():
            texts += [hit["text"] for hit in hits]
        texts += [item["clause"]["text"] for item in grounded.get("checklist", []) if item.get("clause")]
    result = state.cross_lever_result or {}
    for group in result.get("groups", []):
        texts += [hit["text"] for hit in group.get("clauses", [])]
    texts += [hit["text"] for hit in result.get("shared", [])]
    return sorted(set(texts), key=len, reverse=True)


def check_brief(state: SquadState) -> tuple[str, ...]:
    """Returns the issues found in the state's draft, or an empty tuple.

    Playbook clauses quoted word for word are removed first. They state the company's rules, such as
    "offers ... are approved within the Offers Desk", and the citation check already covers them.
    """
    if state.draft is None:
        return ()
    text = brief_text(state)
    for clause in _retrieved_clause_texts(state):
        text = text.replace(clause, " ")
    return check_text(text, org_summary_from(state))
