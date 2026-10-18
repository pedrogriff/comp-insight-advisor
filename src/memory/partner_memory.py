"""Partner feedback memory that lasts beyond one session.

Session memory applies a partner's edit for the rest of the current talent
review, as Checkpoint 1.1 describes. This module keeps edits after the session
ends, in two tables:

1. feedback_events stores every edit the partner makes, with the partner, the
   VP org and the session it came from.
2. standing_preferences stores edits that recur. When the same edit appears in
   MIN_SESSIONS separate sessions, the store proposes it. A proposal changes
   nothing until the partner confirms it. A confirmed preference loads at the
   start of every later session for that partner and org. It goes back to the
   partner for confirmation after REVIEW_AFTER_DAYS, or as soon as the partner
   makes an edit that contradicts it.

The store records only what the partner does, never what memory applied, so a
preference cannot reinforce itself. Memory can narrow or reorder what the
agent shows. It cannot loosen the governance playbook. Keys in POLICY_LOCKED
raise PolicyLockedError, unknown keys raise ValueError, a remembered budget cap
can only lower the ledger figure, and a declined option moves to the end of
the list but stays visible.

Standard library only.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from datetime import date, timedelta
import json
from pathlib import Path
import sqlite3
from typing import Any

MIN_SESSIONS = 3
REVIEW_AFTER_DAYS = 180
ALL_ORGS = "*"


def _is_bool(value: Any) -> bool:
    return isinstance(value, bool)


def _is_positive_amount(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


ALLOWED_KEYS: dict[str, tuple[str, Callable[[Any], bool]]] = {
    "exclude_promoted_last_6m": (
        "Leave employees promoted in the last 6 months out of candidate lists.",
        _is_bool,
    ),
    "exclude_tenure_under_1y": (
        "Leave employees with under 1 year of tenure out of candidate lists.",
        _is_bool,
    ),
    "min_rating_for_grants": (
        "Lowest 2025 rating that can appear in a grant option.",
        lambda v: v in ("rating_3", "rating_4", "rating_5"),
    ),
    "budget_cap_usd": (
        "Working cap on proactive spend in briefs. Never above the ledger.",
        _is_positive_amount,
    ),
    "min_evidence_for_options": (
        "Weakest evidence strength at which the brief may cost spend options."
        " MODERATE is the default, so memory can only raise the bar.",
        lambda v: v in ("MODERATE", "STRONG"),
    ),
    "rank_last_option": (
        "An option the partner keeps declining. Shown last, never hidden.",
        lambda v: isinstance(v, str) and bool(v.strip()),
    ),
    "brief_detail": (
        "Length of the brief.",
        lambda v: v in ("summary", "detailed"),
    ),
}

# Keys that can hold several values at once. Every other key holds one value
# per partner and scope, so a new value replaces the old one.
MULTI_VALUE_KEYS = frozenset({"rank_last_option"})

POLICY_LOCKED: dict[str, str] = {
    "skip_manager_inversion_audit": "Playbook Section 4 requires the manager"
    " inversion audit before any recommendation.",
    "skip_stale_promotion_check": "Playbook Section 4 requires the stale"
    " promotion band check.",
    "skip_ledger_reconciliation": "Playbook Section 4 requires the ledger check"
    " before new proactive allocations.",
    "waive_tier3_approval": "Playbook Section 3 requires VP and Head of"
    " Compensation approval for every Tier 3 grant.",
    "raise_budget_cap": "The department ledger sets the ceiling. Memory can"
    " only lower it.",
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS feedback_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    partner_id TEXT NOT NULL,
    vp_org_code TEXT NOT NULL,
    session_id TEXT NOT NULL,
    recorded_on TEXT NOT NULL,
    pref_key TEXT NOT NULL,
    pref_value TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS standing_preferences (
    pref_id INTEGER PRIMARY KEY AUTOINCREMENT,
    partner_id TEXT NOT NULL,
    vp_org_code TEXT NOT NULL,
    pref_key TEXT NOT NULL,
    pref_value TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('proposed', 'active', 'retired')),
    session_count INTEGER NOT NULL,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    confirmed_on TEXT,
    review_by TEXT,
    needs_review INTEGER NOT NULL DEFAULT 0,
    retired_on TEXT,
    retired_reason TEXT,
    UNIQUE (partner_id, vp_org_code, pref_key, pref_value)
);
"""


class PolicyLockedError(ValueError):
    """Raised when feedback tries to switch off a governance rule."""


@dataclass(frozen=True)
class Preference:
    """One standing preference, as stored."""

    pref_id: int
    partner_id: str
    vp_org_code: str
    key: str
    value: Any
    status: str
    session_count: int
    first_seen: str
    last_seen: str
    confirmed_on: str | None
    review_by: str | None
    needs_review: bool


def _validate(key: str, value: Any) -> None:
    if key in POLICY_LOCKED:
        raise PolicyLockedError(f"{key}: {POLICY_LOCKED[key]}")
    if key not in ALLOWED_KEYS:
        raise ValueError(f"unknown preference key {key!r}")
    if not ALLOWED_KEYS[key][1](value):
        raise ValueError(f"invalid value {value!r} for {key}")


def _to_preference(row: sqlite3.Row) -> Preference:
    return Preference(
        pref_id=row["pref_id"],
        partner_id=row["partner_id"],
        vp_org_code=row["vp_org_code"],
        key=row["pref_key"],
        value=json.loads(row["pref_value"]),
        status=row["status"],
        session_count=row["session_count"],
        first_seen=row["first_seen"],
        last_seen=row["last_seen"],
        confirmed_on=row["confirmed_on"],
        review_by=row["review_by"],
        needs_review=bool(row["needs_review"]),
    )


class PartnerMemory:
    """SQLite store for partner feedback events and standing preferences."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn, conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def record_feedback(
        self,
        partner_id: str,
        vp_org_code: str,
        session_id: str,
        key: str,
        value: Any,
        recorded_on: date | None = None,
        note: str = "",
    ) -> Preference | None:
        """Stores one partner edit.

        Returns the proposal this edit created or brought back, or None. Use
        vp_org_code ALL_ORGS for an edit that applies to every VP org.
        """
        _validate(key, value)
        day = (recorded_on or date.today()).isoformat()
        encoded = json.dumps(value, sort_keys=True)
        scope = (partner_id, vp_org_code, key)
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO feedback_events (partner_id, vp_org_code, session_id,"
                " recorded_on, pref_key, pref_value, note) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (partner_id, vp_org_code, session_id, day, key, encoded, note),
            )
            if key not in MULTI_VALUE_KEYS:
                conn.execute(
                    "UPDATE standing_preferences SET needs_review = 1"
                    " WHERE partner_id = ? AND vp_org_code = ? AND pref_key = ?"
                    " AND pref_value != ? AND status = 'active'",
                    (*scope, encoded),
                )
            existing = conn.execute(
                "SELECT * FROM standing_preferences WHERE partner_id = ?"
                " AND vp_org_code = ? AND pref_key = ? AND pref_value = ?",
                (*scope, encoded),
            ).fetchone()
            since = existing["retired_on"] if existing and existing["status"] == "retired" else None
            seen = conn.execute(
                "SELECT COUNT(DISTINCT session_id) AS sessions, MIN(recorded_on) AS first_seen,"
                " MAX(recorded_on) AS last_seen FROM feedback_events WHERE partner_id = ?"
                " AND vp_org_code = ? AND pref_key = ? AND pref_value = ?"
                " AND (? IS NULL OR recorded_on > ?)",
                (*scope, encoded, since, since),
            ).fetchone()
            if existing is None:
                if seen["sessions"] < MIN_SESSIONS:
                    return None
                cur = conn.execute(
                    "INSERT INTO standing_preferences (partner_id, vp_org_code, pref_key,"
                    " pref_value, status, session_count, first_seen, last_seen)"
                    " VALUES (?, ?, ?, ?, 'proposed', ?, ?, ?)",
                    (*scope, encoded, seen["sessions"], seen["first_seen"], seen["last_seen"]),
                )
                pref_id = cur.lastrowid
            elif existing["status"] == "retired":
                if seen["sessions"] < MIN_SESSIONS:
                    return None
                pref_id = existing["pref_id"]
                conn.execute(
                    "UPDATE standing_preferences SET status = 'proposed', session_count = ?,"
                    " first_seen = ?, last_seen = ?, confirmed_on = NULL, review_by = NULL,"
                    " needs_review = 0, retired_on = NULL, retired_reason = NULL"
                    " WHERE pref_id = ?",
                    (seen["sessions"], seen["first_seen"], seen["last_seen"], pref_id),
                )
            else:
                pref_id = existing["pref_id"]
                conn.execute(
                    "UPDATE standing_preferences SET session_count = ?, last_seen = ?"
                    " WHERE pref_id = ?",
                    (seen["sessions"], seen["last_seen"], pref_id),
                )
                if existing["status"] == "active":
                    return None
            row = conn.execute(
                "SELECT * FROM standing_preferences WHERE pref_id = ?", (pref_id,)
            ).fetchone()
        return _to_preference(row)

    def confirm(
        self, pref_id: int, partner_id: str, confirmed_on: date | None = None
    ) -> Preference:
        """Activates a proposal, or renews an active preference, after the partner says yes."""
        day = confirmed_on or date.today()
        with closing(self._connect()) as conn, conn:
            row = conn.execute(
                "SELECT * FROM standing_preferences WHERE pref_id = ? AND partner_id = ?",
                (pref_id, partner_id),
            ).fetchone()
            if row is None or row["status"] == "retired":
                raise ValueError(f"no open preference {pref_id} for partner {partner_id}")
            if row["pref_key"] not in MULTI_VALUE_KEYS:
                conn.execute(
                    "UPDATE standing_preferences SET status = 'retired', retired_on = ?,"
                    " retired_reason = ? WHERE partner_id = ? AND vp_org_code = ?"
                    " AND pref_key = ? AND pref_id != ? AND status != 'retired'",
                    (
                        day.isoformat(),
                        f"replaced by preference {pref_id}",
                        partner_id,
                        row["vp_org_code"],
                        row["pref_key"],
                        pref_id,
                    ),
                )
            conn.execute(
                "UPDATE standing_preferences SET status = 'active', confirmed_on = ?,"
                " review_by = ?, needs_review = 0 WHERE pref_id = ?",
                (
                    day.isoformat(),
                    (day + timedelta(days=REVIEW_AFTER_DAYS)).isoformat(),
                    pref_id,
                ),
            )
            row = conn.execute(
                "SELECT * FROM standing_preferences WHERE pref_id = ?", (pref_id,)
            ).fetchone()
        return _to_preference(row)

    def retire(
        self, pref_id: int, partner_id: str, reason: str, retired_on: date | None = None
    ) -> None:
        """Stops applying a preference. MIN_SESSIONS new sessions can propose it again."""
        day = (retired_on or date.today()).isoformat()
        with closing(self._connect()) as conn, conn:
            cur = conn.execute(
                "UPDATE standing_preferences SET status = 'retired', retired_on = ?,"
                " retired_reason = ? WHERE pref_id = ? AND partner_id = ?",
                (day, reason, pref_id, partner_id),
            )
            if cur.rowcount == 0:
                raise ValueError(f"no preference {pref_id} for partner {partner_id}")

    def load_for_session(
        self, partner_id: str, vp_org_code: str, today: date | None = None
    ) -> dict[str, list[Preference]]:
        """Returns the preferences to apply now and the ones to ask about first.

        "apply" holds confirmed, current preferences. An org-specific value
        beats an ALL_ORGS value for the same key. "ask_partner" holds
        proposals, preferences past their review date and preferences a later
        edit contradicted. None of those apply until the partner confirms them.
        """
        day = (today or date.today()).isoformat()
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT * FROM standing_preferences WHERE partner_id = ?"
                " AND vp_org_code IN (?, ?) AND status != 'retired'"
                " ORDER BY vp_org_code = ? DESC, pref_id",
                (partner_id, vp_org_code, ALL_ORGS, vp_org_code),
            ).fetchall()
        apply: list[Preference] = []
        ask: list[Preference] = []
        for pref in map(_to_preference, rows):
            current = (
                pref.status == "active"
                and not pref.needs_review
                and pref.review_by is not None
                and day <= pref.review_by
            )
            if not current:
                ask.append(pref)
            elif pref.key in MULTI_VALUE_KEYS:
                if all(p.value != pref.value for p in apply if p.key == pref.key):
                    apply.append(pref)
            elif all(p.key != pref.key for p in apply):
                apply.append(pref)
        return {"apply": apply, "ask_partner": ask}


def effective_budget_cap(preferences: list[Preference], ledger_remaining_usd: float) -> float:
    """Returns the lower of the remembered cap and the ledger. Memory never raises the cap."""
    caps = [p.value for p in preferences if p.key == "budget_cap_usd"]
    return min([ledger_remaining_usd, *caps])


def order_options(
    options: list[dict[str, Any]],
    preferences: list[Preference],
    id_field: str = "branch_id",
) -> list[dict[str, Any]]:
    """Moves options the partner keeps declining to the end. Every option stays in the list."""
    declined = {p.value: p for p in preferences if p.key == "rank_last_option"}
    kept = [o for o in options if o[id_field] not in declined]
    moved = [
        {
            **o,
            "memory_note": f"Declined in {declined[o[id_field]].session_count}"
            " earlier sessions. Shown last at the partner's standing request.",
        }
        for o in options
        if o[id_field] in declined
    ]
    return kept + moved
