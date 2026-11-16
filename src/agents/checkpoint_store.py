"""Durable per-thread checkpoints in SQLite.

ThreadCheckpointer in state.py keeps snapshots in memory, so a brief waiting
for a person disappears when the process ends. SqliteThreadCheckpointer has
the same save(), history() and latest() calls and writes every snapshot to a
SQLite file, so a held or paused run survives a restart and load_state()
rebuilds the typed SquadState exactly as it was saved.
"""

from __future__ import annotations

from contextlib import closing
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import time

from src.agents import serialization
from src.agents.state import SquadState, StepSnapshot

SCHEMA = """
CREATE TABLE IF NOT EXISTS checkpoints (
    thread_id TEXT NOT NULL,
    step INTEGER NOT NULL,
    node TEXT NOT NULL,
    status TEXT NOT NULL,
    findings_count INTEGER NOT NULL,
    revisions INTEGER NOT NULL,
    messages_count INTEGER NOT NULL,
    saved_at TEXT NOT NULL,
    elapsed_ms REAL NOT NULL,
    state_json TEXT NOT NULL,
    PRIMARY KEY (thread_id, step)
)
"""


class SqliteThreadCheckpointer:
    """Drop-in for ThreadCheckpointer that keeps every node's snapshot on disk."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._last_save: dict[str, float] = {}
        with closing(self._connect()) as conn, conn:
            conn.execute(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path, timeout=30)

    def save(self, thread_id: str, node: str, state: SquadState) -> StepSnapshot:
        now = time.perf_counter()
        elapsed_ms = round((now - self._last_save.get(thread_id, now)) * 1000, 3)
        self._last_save[thread_id] = now
        payload = serialization.dumps(state)
        with closing(self._connect()) as conn, conn:
            step = conn.execute(
                "SELECT COALESCE(MAX(step), 0) + 1 FROM checkpoints WHERE thread_id = ?", (thread_id,)
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO checkpoints VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    thread_id,
                    step,
                    node,
                    state.status,
                    len(state.findings),
                    state.revisions,
                    len(state.messages),
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    elapsed_ms,
                    payload,
                ),
            )
        return StepSnapshot(
            step=step,
            node=node,
            status=state.status,
            findings_count=len(state.findings),
            revisions=state.revisions,
            messages_count=len(state.messages),
            state_copy=asdict(serialization.loads(payload)),
        )

    def history(self, thread_id: str) -> list[StepSnapshot]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT step, node, status, findings_count, revisions, messages_count, state_json "
                "FROM checkpoints WHERE thread_id = ? ORDER BY step",
                (thread_id,),
            ).fetchall()
        return [
            StepSnapshot(
                step=row[0],
                node=row[1],
                status=row[2],
                findings_count=row[3],
                revisions=row[4],
                messages_count=row[5],
                state_copy=asdict(serialization.loads(row[6])),
            )
            for row in rows
        ]

    def latest(self, thread_id: str) -> StepSnapshot | None:
        steps = self.history(thread_id)
        return steps[-1] if steps else None

    def load_state(self, thread_id: str, step: int | None = None) -> SquadState | None:
        """Rebuilds the typed state of a thread's latest step, or of one named step."""
        query = "SELECT state_json FROM checkpoints WHERE thread_id = ?"
        params: tuple = (thread_id,)
        if step is not None:
            query += " AND step = ?"
            params += (step,)
        query += " ORDER BY step DESC LIMIT 1"
        with closing(self._connect()) as conn:
            row = conn.execute(query, params).fetchone()
        return serialization.loads(row[0]) if row else None

    def timings(self, thread_id: str) -> list[dict[str, object]]:
        """Node name and milliseconds since the previous snapshot, for the trace view."""
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT step, node, status, saved_at, elapsed_ms FROM checkpoints WHERE thread_id = ? ORDER BY step",
                (thread_id,),
            ).fetchall()
        return [
            {"step": r[0], "node": r[1], "status": r[2], "saved_at": r[3], "elapsed_ms": r[4]} for r in rows
        ]

    def threads(self) -> list[dict[str, object]]:
        """One row per thread with its latest node and status."""
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT c.thread_id, c.step, c.node, c.status, c.saved_at FROM checkpoints c "
                "JOIN (SELECT thread_id, MAX(step) AS step FROM checkpoints GROUP BY thread_id) m "
                "ON c.thread_id = m.thread_id AND c.step = m.step ORDER BY c.saved_at, c.thread_id"
            ).fetchall()
        return [
            {"thread_id": r[0], "steps": r[1], "node": r[2], "status": r[3], "saved_at": r[4]} for r in rows
        ]
