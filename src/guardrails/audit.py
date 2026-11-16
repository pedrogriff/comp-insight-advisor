"""Append-only audit log with a hash chain.

Every guarded run writes one JSON line per step: the request, the screen's
verdict, each tool call, the verifier's result, the monitor's flags, the risk
route, and every human decision. Each line carries the SHA-256 of the line
before it, so a changed or deleted line breaks the chain and verify_chain()
names the first bad line. The log answers what the agent did, in what order,
on whose request and who approved it.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import threading
from typing import Any

try:  # File locks keep the chain intact across processes. Windows has no fcntl, so it relies on the thread lock.
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]

GENESIS = "0" * 64


def _digest(record: dict[str, Any]) -> str:
    body = {key: value for key, value in record.items() if key != "hash"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode("utf-8")).hexdigest()


class AuditLog:
    """Writes hash-chained JSON lines to one file.

    Each write reads the file's last line under a lock first, so several advisor objects, or several
    processes, can share one log without breaking the chain.
    """

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    @staticmethod
    def _last_record(handle: Any) -> tuple[int, str]:
        handle.seek(0, 2)
        size = handle.tell()
        if size == 0:
            return 0, GENESIS
        step = 4096
        tail = b""
        while True:
            start = max(0, size - step)
            handle.seek(start)
            tail = handle.read(size - start)
            lines = [line for line in tail.split(b"\n") if line.strip()]
            if start == 0 or len(lines) >= 2:
                break
            step *= 2
        last = json.loads(lines[-1].decode("utf-8"))
        return int(last["seq"]), str(last["hash"])

    def record(self, thread_id: str, kind: str, **fields: Any) -> dict[str, Any]:
        with self._lock, self.path.open("a+b") as handle:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                seq, previous = self._last_record(handle)
                record: dict[str, Any] = {
                    "seq": seq + 1,
                    "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                    "thread_id": thread_id,
                    "kind": kind,
                    **fields,
                    "prev": previous,
                }
                record["hash"] = _digest(record)
                handle.seek(0, 2)
                handle.write((json.dumps(record, default=str) + "\n").encode("utf-8"))
                handle.flush()
            finally:
                if fcntl is not None:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        return record

    def read(self, thread_id: str | None = None) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        records = [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]
        return [r for r in records if thread_id is None or r["thread_id"] == thread_id]


def verify_chain(path: Path | str) -> dict[str, Any]:
    """Recomputes the chain. Returns ok, the number of lines and the first bad sequence number."""
    path = Path(path)
    previous = GENESIS
    count = 0
    if not path.exists():
        return {"ok": True, "records": 0, "first_bad_seq": None}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        count += 1
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            return {"ok": False, "records": count, "first_bad_seq": count}
        if record.get("prev") != previous or record.get("hash") != _digest(record) or record.get("seq") != count:
            return {"ok": False, "records": count, "first_bad_seq": record.get("seq", count)}
        previous = record["hash"]
    return {"ok": True, "records": count, "first_bad_seq": None}
