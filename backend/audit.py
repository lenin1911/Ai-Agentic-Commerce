"""
Audit logging engine for Agent Storefront.
Maintains an immutable SQLite ledger capturing every agent action,
state-changing operation, policy evaluation, rejection, and payment event.
"""

from datetime import datetime, timezone
import json
import os
import sqlite3
from typing import Any, Dict, List, Optional

DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "audit.db",
)


class AuditLogger:
    """Manages SQLite-backed audit trails."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.environ.get("AUDIT_DB_PATH", DEFAULT_DB_PATH)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Creates a thread-safe connection to the SQLite database."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Initializes audit table if it does not already exist."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    action TEXT NOT NULL,
                    payload_summary TEXT,
                    policy_result TEXT NOT NULL,
                    reason TEXT,
                    razorpay_ref TEXT
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_session ON audit_logs(session_id)"
            )
            conn.commit()

    def log(
        self,
        session_id: str,
        actor: str,
        action: str,
        payload_summary: Any = None,
        policy_result: str = "N/A",
        reason: Optional[str] = None,
        razorpay_ref: Optional[str] = None,
    ) -> int:
        """
        Inserts an audit record.
        payload_summary can be a dict, str, or primitive; dicts are serialized to JSON.
        """
        timestamp = datetime.now(timezone.utc).isoformat()

        if isinstance(payload_summary, (dict, list)):
            payload_str = json.dumps(payload_summary)
        elif payload_summary is not None:
            payload_str = str(payload_summary)
        else:
            payload_str = ""

        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO audit_logs (
                    timestamp, session_id, actor, action,
                    payload_summary, policy_result, reason, razorpay_ref
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp,
                    session_id or "unknown_session",
                    actor or "buyer_agent",
                    action,
                    payload_str,
                    policy_result,
                    reason or "",
                    razorpay_ref or "",
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def get_entries(
        self,
        session_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Retrieves audit entries, newest first, with optional session filter."""
        with self._get_connection() as conn:
            if session_id:
                cursor = conn.execute(
                    """
                    SELECT * FROM audit_logs
                    WHERE session_id = ?
                    ORDER BY id DESC
                    LIMIT ? OFFSET ?
                    """,
                    (session_id, limit, offset),
                )
            else:
                cursor = conn.execute(
                    """
                    SELECT * FROM audit_logs
                    ORDER BY id DESC
                    LIMIT ? OFFSET ?
                    """,
                    (limit, offset),
                )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def clear(self) -> None:
        """Deletes all audit records (used for test isolation)."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM audit_logs")
            conn.commit()


# Default singleton
_default_audit_logger: Optional[AuditLogger] = None


def get_audit_logger(db_path: Optional[str] = None) -> AuditLogger:
    """Returns or initializes default AuditLogger singleton."""
    global _default_audit_logger
    if db_path is not None:
        return AuditLogger(db_path=db_path)
    if _default_audit_logger is None:
        _default_audit_logger = AuditLogger()
    return _default_audit_logger
