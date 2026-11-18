"""Human-in-the-loop review queue + audit trail.

Answers that are low-confidence, or that a user wants to turn into a controlled
record (e.g. a lessons-learned entry or RFI), go into a review queue. Nothing is
"released" until a named person approves it. Every event is written to an
append-only audit log (JSONL) for traceability.
"""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from . import config


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def audit(event: str, **data) -> None:
    config.AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with config.AUDIT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": _now(), "event": event, **data}) + "\n")


class ReviewQueue:
    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or config.DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    question TEXT NOT NULL,
                    payload TEXT NOT NULL,          -- full structured answer as JSON
                    reason TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',  -- pending | approved | rejected
                    reviewer TEXT,
                    reviewed_at TEXT,
                    comment TEXT
                )""")

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def submit(self, question: str, payload: dict, reason: str) -> int:
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO reviews (created_at, question, payload, reason) VALUES (?, ?, ?, ?)",
                (_now(), question, json.dumps(payload), reason),
            )
            review_id = cur.lastrowid
        audit("review_submitted", review_id=review_id, reason=reason)
        return review_id

    def list(self, status: str | None = "pending") -> list[dict]:
        with self._conn() as c:
            if status:
                rows = c.execute("SELECT * FROM reviews WHERE status=? ORDER BY id", (status,)).fetchall()
            else:
                rows = c.execute("SELECT * FROM reviews ORDER BY id").fetchall()
        return [{**dict(r), "payload": json.loads(r["payload"])} for r in rows]

    def decide(self, review_id: int, approve: bool, reviewer: str, comment: str = "") -> dict:
        if not reviewer.strip():
            raise ValueError("A named reviewer is required.")
        new_status = "approved" if approve else "rejected"
        with self._conn() as c:
            row = c.execute("SELECT status FROM reviews WHERE id=?", (review_id,)).fetchone()
            if row is None:
                raise KeyError(f"Review {review_id} not found")
            if row["status"] != "pending":
                raise ValueError(f"Review {review_id} is already {row['status']}")
            c.execute(
                "UPDATE reviews SET status=?, reviewer=?, reviewed_at=?, comment=? WHERE id=?",
                (new_status, reviewer, _now(), comment, review_id),
            )
        audit("review_decided", review_id=review_id, status=new_status, reviewer=reviewer, comment=comment)
        return {"id": review_id, "status": new_status, "reviewer": reviewer}
