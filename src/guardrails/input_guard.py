"""Request screen: the guardrail that runs before any agent or tool.

screen_request() checks a partner's request against named rules, in a fixed
order, and returns allow, refuse or clarify with the rule that fired. The
rules are plain code, so a refusal needs no model call and the same request
always gets the same answer.

Rules, in order:
- empty, oversized: nothing to answer, or more text than a request needs.
- injection: text that tries to change the agent's instructions or switch off
  a check.
- protected_attribute: pay analysis by age, gender, origin or a similar trait.
- individual_pay: one named person's or one employee ID's pay. Briefs are
  cohort level.
- write_action: an order to approve, issue, change or send something. The
  advisor prepares analysis and a person decides.
- out_of_scope: nothing about pay, retention, offers or the playbook.
- unknown_scope: a VP org or job family the data does not hold.
- cross_org: a VP org outside the requesting partner's scope. The scope comes
  from the session, never from the request text.

The screen reads wording, so it tells an order ("Approve the Tier 3 grants")
from a question ("Who approves Tier 3 grants?") by where the verb sits in
its clause. It is a first filter. The tool scopes, the verifier and the
approval gate behind it do not depend on it.

Version 2 of the rules. Version 1 passed all 40 of its author's cases and 35
of 48 cases a separate agent wrote from the policy alone, letting 10 of 30
violations through, most of them disguised. Version 2 adds what those misses
showed: typo-tolerant keywords, softer ways to ask for an unchecked answer,
role play, age and work-permit wording, pronouns that point at one person,
and indirect orders. python3 -m src.guardrails.evaluate reports every split.

From the repo root:
    python3 -m src.guardrails.input_guard "Ignore previous instructions" VP_CLOUD_AI
"""

from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
import re
import sys

from src.tools.deterministic_analytics import DEFAULT_DB_PATH, connect_readonly

MAX_REQUEST_CHARS = 2000

ALLOW = "allow"
REFUSE = "refuse"
CLARIFY = "clarify"


@dataclass(frozen=True)
class PartnerContext:
    """Who is asking and which VP orgs they may see. Set by the session, never by a model."""

    partner_id: str
    allowed_orgs: tuple[str, ...]
    role: str = "compensation_partner"


@dataclass(frozen=True)
class InputVerdict:
    """Result of the request screen."""

    decision: str  # allow, refuse or clarify
    rule: str
    message: str
    matched: str = ""


SCOPE_NOTICE = (
    "This advisor prepares retention and offer briefs for a VP org or job family at Apex Cloud & AI Corp, "
    "and answers questions about the compensation governance playbook. It works at cohort level on "
    "synthetic data, and a compensation partner decides what happens next."
)

# Words that can open a clause before its verb, as in "please go ahead and approve".
LEAD = (
    r"^(?:(?:please|pls|plz|kindly|now|then|also|and|just|so|ok|okay|hey|hi|great|thanks|first|next|finally|"
    r"quickly|meanwhile|afterwards|instead)[\s,]+|(?:just this once|this time|for now|straight away|right away|"
    r"once that's done|when you're done|after that)[\s,]+|"
    r"(?:go ahead and|you can|you should|you must|you need to|i need you to|i want you to|i would like you to|"
    r"i'd like you to|can you|could you|would you|will you|we need you to|let's|lets|let us|make sure to|"
    r"make sure you|be sure to|feel free to)\s+)*"
)

# --- injection: the text addresses the assistant's own instructions or checks.
ASSISTANT_TARGETS = (
    r"(instructions?|rules|guardrails?|prompts?|checks?|constraints|guidelines|restrictions|safeguards|"
    r"limits|policies|programming|training)"
)
CHECK_TARGETS = (
    r"(verifier|verification|governance reviewer|reviewer|guardrails?|approval gate|approval step|approvals?|"
    r"sign-?offs?|citations?|checks?|safeguards|human review|review step|audit log|logging)"
)
INJECTION_PATTERNS = (
    r"\b(ignore|disregard|forget|override|drop|abandon)\b.{0,30}\b(your|all|any|previous|prior|above|earlier|"
    r"the system|these|those|every)\b.{0,25}\b" + ASSISTANT_TARGETS + r"\b",
    r"\b(ignore|disregard|override)\b.{0,20}\bthe\s+" + CHECK_TARGETS + r"\b",
    r"\b(system prompt|developer mode|debug mode|admin mode|god mode|jailbreak|do anything now)\b",
    r"\byou are now\b|\bact as (if|though) you\b|\bpretend (that )?(you|there)\b|\bnew instructions?\b",
    r"\bfrom now on\b.{0,40}\b(you|respond|answer|act|behave|ignore|skip|stop|never|always)\b",
    r"^\s*(system|assistant|developer|admin)\s*:",
    r"\b" + CHECK_TARGETS + r"\b.{0,25}\b(is|are|has been|have been|was)\s+(now\s+)?(disabled|off|suspended|"
    r"turned off|switched off|waived|not needed|unnecessary|optional)\b",
    r"\b(mark|set|label|stamp|flag)\b.{0,25}\b(as\s+)?(approved|verified|signed off|cleared)\b",
    r"\b(output|return|give|send|release|publish|print|respond|answer|write)\b.{0,40}\b(unverified|unchecked|"
    r"without (any\s+)?(verification|verifying|checks?|checking|citations?|citing|review|sign-?offs?|approval))\b",
    r"\b(reveal|show|print|repeat|display|leak|dump)\b.{0,30}\b(your|the system|the hidden|the original)\b"
    r".{0,15}\b(prompt|instructions|rules)\b",
    r"\bwhat (are|were) your (instructions|rules|system prompt)\b",
    r"\b(ignore|disregard|forget)\b.{0,25}\b(everything|anything|all|what(ever)?)\b.{0,25}\b(you were|you've been|"
    r"you have been)\s+(told|given|instructed|taught)\b",
    r"\b(hidden|secret|original|initial)\s+(instructions?|prompts?|rules)\b",
    r"\b(exact wording|word for word|verbatim)\b.{0,80}\b(set up|configured|instructed|told|given|prompted)\b|"
    r"\byou were (set up|configured|initialized) with\b|\breproduce\b.{0,40}\b(instructions|prompt|wording|setup)\b",
    r"\b(treat|consider|assume|count|regard|take)\b.{0,50}\b(sign-?offs?|approvals?|review|verification|checks?)\b"
    r".{0,30}\b(already\s+)?(done|complete|completed|given|granted|approved|handled|cleared|obtained|in place)\b",
    r"\b(don't|do not|dont|never|no need to)\s+(run|apply|use|do|put|send|pass|bother)\b.{0,50}\b(checker|verifier|"
    r"checks?|verification|reviewer|review step|gate)\b",
    r"\b(imagine|pretend|suppose)\s+(that\s+)?(you're|you are|you were|youre)\b|\bversion of you\b|"
    r"\bstay(ing)? in (that\s+|this\s+)?character\b|\bstamp it (final|approved|done)\b|\bthought experiment\b",
    r"\bnote (from|to)\b.{0,40}\b(assistant|system|developer|dev team|admin|ai)\b|\bto the assistant\b",
    r"\b(no|without|don't|do not|dont|never)\b.{0,15}\b(need for|bother with|run|apply|use|do)\b.{0,15}\bthe\s+"
    + CHECK_TARGETS + r"\b",
)
# Clause-initial orders to switch a check off. A question such as "Can we skip the level review?" is policy.
INJECTION_ORDERS = (
    LEAD + r"(skip|bypass|disable|turn off|switch off|circumvent|suppress|remove|omit|waive)\s+(?:(?:the|all|any|"
    r"every|your|that|this)\s+)*(?:[\w-]+\s+){0,2}?" + CHECK_TARGETS + r"\b",
    LEAD + r"(leave out|drop|omit|exclude|strip|remove|don't include|do not include|dont include|don't mention|"
    r"do not mention|don't bring up|do not bring up|don't cite|do not cite)\s+(?:(?:the|all|any|every|your|that|"
    r"this|those)\s+)*(?:[\w-]+\s+){0,2}?(references?|citations?|sources?|clause ids?|sign-?offs?|disclosures?|"
    r"caveats?|checks?|review|verification)\b",
)
# Critical words that a typo must not hide. A word one edit away from one of these is read as that word.
TYPO_KEYWORDS = ("ignore", "issue", "approve", "bypass", "disregard", "override", "authorize", "instructions",
                 "disable", "everything")
NOT_TYPOS = frozenset("tissue issues issued issuer ignored ignores approved approves approver bypassed overrode "
                      "overrides authorized authorizes instruction disabled disables grand".split())

# --- protected_attribute
PROTECTED_PATTERNS = (
    r"\b(gender|genders|sex|women|woman|female|females|male|males|men|ethnic|ethnicity|ethnicities|racial|"
    r"nationality|nationalities|national origin|religion|religious|pregnan\w*|maternity|paternity|"
    r"parental leave|disabilit\w*|marital status|married|unmarried|sexual orientation|veteran status|veterans|"
    r"citizenship|immigration status|visa status|visa holders?|h-?1b)\b",
    r"\b(by|on|of|their|employees'|employee's|based on)\s+race\b|\brace\s+(or|and|,)\s",
    r"\b(employees|people|staff|workers|engineers|scientists|candidates|anyone|those|folks|hires)\s+(over|under|"
    r"above|below|older than|younger than|past)\s+\d{2}\b(?!\s*(%|percent|k\b|th\b|st\b|nd\b|rd\b))",
    r"\b(older|younger|aging|elderly)\s+(employees|workers|staff|people|engineers|scientists|candidates|folks|"
    r"hires)\b",
    r"\bby age\b|\bage (group|bracket|band|range)s?\b|\b(their|employee|employees'|candidate) ages?\b|"
    r"\bnear(ing)? retirement\b",
    r"\bin (their|his|her)\s+(early\s+|mid\s+|late\s+)?(twenties|thirties|forties|fifties|sixties|seventies|\d0s)\b|"
    r"\b(will|about to|close to|going to|due to)\s+retire\b|\bretire (within|in|soon)\b",
    r"\b(work permits?|sponsored (visas?|permits?|employees?|workers?|staff)|visa sponsorship|sponsorship status|"
    r"green cards?|on a visa|on visas)\b",
)

# --- individual_pay
PAY_WORDS = (
    r"(salary|salaries|pay|paid|earn|earns|earning|earnings|make|makes|making|compensation|comp|bonus|equity|"
    r"package|cashflow|compa|raise|underpaid|overpaid)"
)
PERSON_NOUNS = r"(people|person|employees?|individuals?|engineers?|scientists?|managers?|staff|workers?|reports?)"
NAME = r"[A-Z][a-z]+\s+[A-Z][a-z]+"
INDIVIDUAL_PATTERNS = (
    r"\bEMP\d{4,6}\b",
    r"\b(highest|lowest|best|worst|top|least|most)[- ]paid\s+" + PERSON_NOUNS + r"\b",
    r"\bby name\b|\bname by name\b|\bwith (their\s+)?names\b",
    r"\bnames? of\b.{0,40}\b" + PERSON_NOUNS + r"\b",
    r"\bwho\s+(earns|is paid|gets paid)\b|\bwho\s+makes\s+(the\s+)?(most|least|more|less)\b",
    r"\bmy\s+(own\s+)?(salary|pay|raise|bonus|equity|compensation|comp|package|compa-?ratio)\b",
    r"\b(my|our|his|her|their)\s+(colleague|coworker|co-worker|teammate|manager|boss|peer|direct report|"
    r"neighbor|friend)('s)?\b.{0,40}\b" + PAY_WORDS + r"\b",
    r"\b(our|my)\s+(?:[\w-]+\s+){0,3}(director|manager|vp|lead|head|engineer|scientist|designer|analyst)'s\s+"
    r"(?:\w+\s+){0,2}" + PAY_WORDS + r"\b",
    r"\b(his|her)\s+(?:\w+\s+){0,1}(band|salary|pay|compensation|comp|equity|bonus|package|raise|compa-?ratio|"
    r"cashflow|grant|offer)\b|\bbring (him|her) up\b|\b(pay|paying|give|giving) (him|her)\b",
    r"\bnames\b.{0,25}\b(and|with|plus)\b.{0,25}\b(dollars?|amounts?|salar\w+|pay|figures|numbers)\b",
    r"\bwhich\s+(?:\w+\s+){0,2}" + PERSON_NOUNS + r"\b.{0,40}\b(lose|loses|earn|earns|make|makes|get|gets|is paid|"
    r"are paid)\b.{0,20}\b(most|least|more|less)\b",
    NAME + r"\s+(?i:feels|is|was|seems|looks|thinks (?:he|she) is)\s+(?i:underpaid|overpaid|under market|below band)\b",
    r"(?i:\bhow much (?:does|did|do|will|is))\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\s+(?i:make|earn|get paid|get|paid)\b",
    r"\b" + NAME + r"'s\s+(?i:(?:\w+\s+){0,2}" + PAY_WORDS + r")\b",
    r"(?i:\b" + PAY_WORDS + r"\s+(?:\w+\s+){0,3}(?:of|for))\s+" + NAME + r"\b",
    r"(?i:\b(?:is|are|was))\s+" + NAME + r"\s+(?i:underpaid|overpaid|paid|earning|making)\b",
)
# Capitalized words that belong to the domain, not to a person's name.
NOT_NAME_WORDS = frozenset(
    """apex cloud corp offers desk head compensation partner partners strategic people vice president tier
    market reference point annual equity refresh key talent award intended cashflow peer percentile base salary
    research scientists scientist security engineers engineer engineering software product managers manager
    designers analysts staff team teams hires employees leaders directors org orgs budget grants grant option
    options section playbook proactive reactive retention counter offer senior junior principal lead new current
    site reliability threat data systems network technical program cyber operations machine learning""".split()
)

# --- write_action: clause-initial orders only.
CLEAR_VERBS = r"(approve|authorize|execute|implement|pay out|sign off on|finalize|greenlight|green-light|enact)"
NOUN_VERBS = r"(issue|grant|award|process|book|commit|release|fund|cut)"
DET = r"(?:the|these|those|all|this|that|a|an|my|our|every|each|both)"
PAY_OBJECTS = (
    r"(grants?|awards?|raises?|increases?|adjustments?|promotions?|counter-?offers?|offers?|bonus(?:es)?|"
    r"payouts?|payments?|options?|plans?|tier\s*3|exceptions?|packages?|checks?|equity|refresh(?:es)?)"
)
CHANGE_VERBS = (
    r"(update|change|edit|modify|overwrite|delete|amend|adjust|increase|decrease|raise|lower|bump|set|top up|"
    r"move|shift|transfer|reallocate|pull|take)"
)
RECORD_OBJECTS = (
    r"(salar(?:y|ies)|pay|records?|roster|database|ledger|budgets?|hr system|hris|payroll|system of record|"
    r"bands?|compa-?ratios?|levels?|ratings?|table|pools?|funds?|allocations?|line)"
)
SEND_VERBS = r"(email|e-mail|send|forward|share|cc|post|circulate|distribute)"
TELL_VERBS = r"(notify|message|slack|text|ping|alert|tell|inform|email|e-mail)"
THIRD_PARTIES = (
    r"(vp|vps|vice president|payroll|finance|employee|employees|candidate|candidates|manager|managers|"
    r"head of compensation|committee|hr|hris|recruiter|recruiters|leadership|execs?|executives?|board|ceo|cfo)"
)
WRITE_PATTERNS = (
    LEAD + CLEAR_VERBS + r"\s+(?:" + DET + r"\s+)?(?:[\w$,.-]+\s+){0,5}?" + PAY_OBJECTS + r"\b",
    LEAD + NOUN_VERBS + r"\s+" + DET + r"\s+(?:[\w$,.-]+\s+){0,5}?" + PAY_OBJECTS + r"\b",
    LEAD + CHANGE_VERBS + r"\s+(?!me\b|us\b)(?:" + DET + r"\s+)?(?:[\w$,.'-]+\s+){0,5}?" + RECORD_OBJECTS + r"\b",
    LEAD + SEND_VERBS + r"\b.{0,60}\bto\s+(?:the\s+|our\s+|my\s+|all\s+|every\s+)?" + THIRD_PARTIES + r"\b",
    LEAD + TELL_VERBS + r"\s+(?:the\s+|our\s+|my\s+|all\s+|every\s+)?" + THIRD_PARTIES + r"\b",
    LEAD + r"(loop in|bring in|copy in|cc)\s+(?:the\s+|our\s+|my\s+|all\s+)?" + THIRD_PARTIES + r"\b",
    LEAD + r"let\s+(?:the\s+|our\s+|my\s+|all\s+)?(?:[\w-]+\s+){0,3}?" + THIRD_PARTIES + r"\s+know\b",
)

# --- out_of_scope: one strong domain term, two general ones, or a VP org code.
STRONG_TERMS = frozenset(
    """retention retain attrition departure departures resign resignations turnover compensation salary salaries
    bonus bonuses equity grant grants refresh vesting vest cashflow cliff cliffs compa compa-ratio percentile
    promotion promotions promoted playbook counter counters countered counter-offer counter-offers candidate
    candidates hiring new-hire cohort cohorts headcount inversion inversions underpaid overpaid sign-off sign-offs
    off-cycle out-earn ledger leveling tier tiers""".split()
)
GENERAL_TERMS = frozenset(
    """pay paid offer offers hire hires level levels cost costs market budget budgets brief policy raise raises
    band bands sign signs left leaving leave earn earns talent approval approves approve acceptance governance
    adjustment adjustments recruit recruiting poaching competitor competitors risk vp vps rule rules""".split()
)
ORG_CODE_RE = re.compile(r"\bVP_[A-Z][A-Z_]*\b")

MESSAGES = {
    "empty": "Ask a question about a VP org, a job family or the playbook. " + SCOPE_NOTICE,
    "oversized": f"Keep the request under {MAX_REQUEST_CHARS} characters. " + SCOPE_NOTICE,
    "injection": "This request tries to change the advisor's instructions or switch off a check, so it was "
    "not run. " + SCOPE_NOTICE,
    "protected_attribute": "The advisor holds no demographic data and never uses age, gender, origin or a "
    "similar trait in pay analysis. Take pay equity questions to the pay equity review. " + SCOPE_NOTICE,
    "individual_pay": "The advisor reports cohorts, not one person's pay. Look up an individual in the HR "
    "system of record. " + SCOPE_NOTICE,
    "write_action": "The advisor prepares analysis and never approves, issues, changes or sends anything. "
    "A person decides and acts. " + SCOPE_NOTICE,
    "out_of_scope": "That is outside what this advisor answers. " + SCOPE_NOTICE,
}


def _clauses(text: str) -> list[str]:
    parts = re.split(r"[.!?;:,()\n]+|\s+(?:and then|and also|and|then|but)\s+", text)
    return [p.strip().lower() for p in parts if p and p.strip()]


def _one_edit_apart(word: str, target: str) -> bool:
    """True when word is one insertion, deletion, substitution or adjacent swap away from target."""
    if word == target or abs(len(word) - len(target)) > 1:
        return False
    if len(word) == len(target):
        diff = [i for i, (a, b) in enumerate(zip(word, target)) if a != b]
        if len(diff) == 1:
            return True
        return len(diff) == 2 and diff[1] == diff[0] + 1 and word[diff[0]] == target[diff[1]] \
            and word[diff[1]] == target[diff[0]]
    longer, shorter = (word, target) if len(word) > len(target) else (target, word)
    return any(longer[:i] + longer[i + 1:] == shorter for i in range(len(longer)))


def _fix_typos(text: str) -> str:
    def fix(match: re.Match) -> str:
        word = match.group(0)
        low = word.lower()
        if len(low) < 4 or low in NOT_TYPOS or low in TYPO_KEYWORDS:
            return word
        for target in TYPO_KEYWORDS:
            if _one_edit_apart(low, target):
                return target
        return word

    return re.sub(r"[A-Za-z]+", fix, text)


def _first_match(patterns: tuple[str, ...], text: str, flags: int = re.I) -> str:
    for pattern in patterns:
        hit = re.search(pattern, text, flags)
        if hit:
            return hit.group(0)
    return ""


def _clause_match(patterns: tuple[str, ...], text: str) -> str:
    for clause in _clauses(text):
        hit = _first_match(patterns, clause)
        if hit:
            return hit
    return ""


def _individual_match(question: str, known_people: tuple[str, ...]) -> str:
    low = question.lower()
    for person in known_people:
        if person.lower() in low and re.search(r"\b" + PAY_WORDS + r"\b", low):
            return person
    # Lowercase capitalized domain words, so "Research Scientists" never reads as a person's name.
    scrubbed = re.sub(
        r"\b[A-Z][a-z]+\b",
        lambda m: m.group(0).lower() if m.group(0).lower() in NOT_NAME_WORDS else m.group(0),
        question,
    )
    for pattern in INDIVIDUAL_PATTERNS:
        # Name patterns rely on capital letters, so they run case-sensitively.
        flags = 0 if "[A-Z]" in pattern else re.I
        hit = re.search(pattern, scrubbed, flags)
        if hit:
            return hit.group(0)
    return ""


def _in_domain(question: str) -> bool:
    if ORG_CODE_RE.search(question):
        return True
    words = set(re.findall(r"[a-z][a-z-]*", question.lower()))
    return bool(words & STRONG_TERMS) or len(words & GENERAL_TERMS) >= 2


def load_scope(db_path: Path | str = DEFAULT_DB_PATH) -> dict[str, tuple[str, ...]]:
    """VP org codes and their job families, read from the roster."""
    with closing(connect_readonly(db_path)) as conn:
        rows = conn.execute(
            "SELECT DISTINCT vp_org_code, job_family FROM org_roster_cashflows ORDER BY 1, 2"
        ).fetchall()
    scope: dict[str, list[str]] = {}
    for org, family in rows:
        scope.setdefault(org, []).append(family)
    return {org: tuple(families) for org, families in scope.items()}


def load_known_people(db_path: Path | str = DEFAULT_DB_PATH) -> tuple[str, ...]:
    """Names of people the data holds, so a request about one of them is recognized."""
    with closing(connect_readonly(db_path)) as conn:
        rows = conn.execute("SELECT DISTINCT vp_leader_name FROM department_budgets ORDER BY 1").fetchall()
    return tuple(r[0] for r in rows if r[0])


def screen_request(
    question: str,
    vp_org_code: str | None = None,
    job_family: str | None = None,
    partner: PartnerContext | None = None,
    db_path: Path | str = DEFAULT_DB_PATH,
    scope: dict[str, tuple[str, ...]] | None = None,
    known_people: tuple[str, ...] | None = None,
) -> InputVerdict:
    """Screens one request. Returns the first rule that fires, or allow."""
    text = (question or "").strip()
    if not text:
        return InputVerdict(CLARIFY, "empty", MESSAGES["empty"])
    if len(text) > MAX_REQUEST_CHARS:
        return InputVerdict(REFUSE, "oversized", MESSAGES["oversized"])

    people = known_people if known_people is not None else load_known_people(db_path)
    fixed = _fix_typos(text)
    for rule, matcher in (
        (
            "injection",
            lambda: _first_match(INJECTION_PATTERNS, fixed, re.I | re.M) or _clause_match(INJECTION_ORDERS, fixed),
        ),
        ("protected_attribute", lambda: _first_match(PROTECTED_PATTERNS, text)),
        ("individual_pay", lambda: _individual_match(text, people)),
        ("write_action", lambda: _clause_match(WRITE_PATTERNS, fixed)),
    ):
        matched = matcher()
        if matched:
            return InputVerdict(REFUSE, rule, MESSAGES[rule], matched)

    known = scope if scope is not None else load_scope(db_path)
    # A valid org chosen in the form already says what the request is about, however it is worded.
    form_in_scope = bool(vp_org_code) and vp_org_code in known
    if not form_in_scope and not _in_domain(text):
        return InputVerdict(REFUSE, "out_of_scope", MESSAGES["out_of_scope"])

    visible = tuple(o for o in known if partner is None or o in partner.allowed_orgs)
    named_orgs = list(dict.fromkeys(([vp_org_code] if vp_org_code else []) + ORG_CODE_RE.findall(text)))
    for org in named_orgs:
        if org not in known:
            return InputVerdict(
                CLARIFY,
                "unknown_scope",
                f"No VP org named {org} exists in the data. Choose one of: {', '.join(visible) or 'none'}.",
                org,
            )
    if job_family and vp_org_code and job_family not in known[vp_org_code]:
        return InputVerdict(
            CLARIFY,
            "unknown_scope",
            f"{vp_org_code} has no job family {job_family}. Choose one of: {', '.join(known[vp_org_code])}.",
            job_family,
        )
    if job_family and not vp_org_code:
        return InputVerdict(CLARIFY, "unknown_scope", "Name the VP org that the job family belongs to.", job_family)
    if partner is not None:
        for org in named_orgs:
            if org not in partner.allowed_orgs:
                return InputVerdict(
                    REFUSE,
                    "cross_org",
                    f"{org} is outside the orgs this session covers "
                    f"({', '.join(partner.allowed_orgs) or 'none'}). Access comes from the session, not from "
                    "the request.",
                    org,
                )
    return InputVerdict(ALLOW, "allowed", "")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        raise SystemExit('Usage: python3 -m src.guardrails.input_guard "question" [VP_ORG] [JOB_FAMILY]')
    verdict = screen_request(args[0], args[1] if len(args) > 1 else None, args[2] if len(args) > 2 else None)
    print(f"{verdict.decision} [{verdict.rule}] {verdict.message}".strip())
