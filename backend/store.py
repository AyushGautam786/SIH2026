"""
store.py — SQLite-backed audit trail (prototype AuditStore implementation).

Swap for PostgresAuditStore in production (see interfaces.py); the two
public methods are the entire contract main.py depends on.
"""
import sqlite3
import time
from pathlib import Path

from interfaces import AuditStore

DB_PATH = Path(__file__).parent / "pulse_audit.db"


class SQLiteAuditStore(AuditStore):
    """Persists every autonomous action to a local SQLite database file.

    Production upgrade: replace with PostgresAuditStore using psycopg2 or
    asyncpg, ideally on a TimescaleDB extension for time-series queries.
    The two method signatures below are the complete API contract.
    """

    def __init__(self, db_path: Path = DB_PATH) -> None:
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_log (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                ts               REAL    NOT NULL,
                container_id     TEXT    NOT NULL,
                container_name   TEXT    NOT NULL,
                pipeline         TEXT    NOT NULL,
                predicted_state  TEXT    NOT NULL,
                confidence       REAL    NOT NULL,
                action           TEXT    NOT NULL
            )
            """
        )
        conn.commit()
        conn.close()

    def log_action(
        self,
        container_id: str,
        container_name: str,
        pipeline: str,
        predicted_state: str,
        confidence: float,
        action: str,
    ) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            INSERT INTO audit_log
                (ts, container_id, container_name, pipeline, predicted_state, confidence, action)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (time.time(), container_id, container_name, pipeline, predicted_state, confidence, action),
        )
        conn.commit()
        conn.close()

    def recent_actions(self, limit: int = 50) -> list[dict]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM audit_log ORDER BY ts DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def total_actions(self) -> int:
        conn = sqlite3.connect(self.db_path)
        count = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
        conn.close()
        return count
