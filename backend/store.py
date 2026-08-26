"""
store.py - SQLite-backed audit trail (prototype AuditStore implementation).

Swap for PostgresAuditStore in production (see interfaces.py); the two
public methods are the entire contract main.py depends on.
"""
import os
import sqlite3
import time
from pathlib import Path

from interfaces import AuditStore

import simulator  # for TICK_SECONDS (retention horizon) - no cycle

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

    def log_escalation(self, container_id, container_name, pipeline,
                       predicted_state, confidence) -> None:
        """Record a circuit-breaker escalation - Pulse detected risk but was
        prevented from acting fleet-wide; surfaced to humans instead."""
        self.log_action(container_id, container_name, pipeline,
                        predicted_state, confidence, "escalate")


class SQLiteMetricsStore:
    """Time-series metrics sink (prototype stand-in for TimescaleDB).

    Writes one row per container per tick so the dashboard can render
    historical charts via GET /api/history/{container_id}. Rows are pruned
    past RETENTION_TICKS to bound file growth."""

    RETENTION_TICKS = 600          # ~30 minutes @3s ticks

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or Path(__file__).parent / "pulse_metrics.db"
        self._init_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS metrics (
                ts           REAL NOT NULL,
                container_id TEXT NOT NULL,
                cpu          REAL NOT NULL,
                mem          REAL NOT NULL,
                net          REAL NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_metrics_cid_ts ON metrics (container_id, ts)"
        )
        conn.commit()
        conn.close()

    def write_tick(self, snapshots: list[dict]) -> None:
        now = time.time()
        conn = sqlite3.connect(self.db_path)
        conn.executemany(
            "INSERT INTO metrics (ts, container_id, cpu, mem, net) VALUES (?, ?, ?, ?, ?)",
            [(now, s["id"], s["cpu"], s["mem"], s["net"]) for s in snapshots],
        )
        conn.execute(
            "DELETE FROM metrics WHERE ts < ?",
            (now - self.RETENTION_TICKS * simulator.TICK_SECONDS,),
        )
        conn.commit()
        conn.close()

    def history(self, container_id: str, points: int = 120) -> list[dict]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT ts, cpu, mem, net FROM metrics
            WHERE container_id = ? ORDER BY ts DESC LIMIT ?
            """,
            (container_id, max(1, min(points, 1000))),
        ).fetchall()
        conn.close()
        return [dict(r) for r in reversed(rows)]


# ---------------------------------------------------------------------------
# Production-grade stores - constructed only when a DSN env var is provided.
# ---------------------------------------------------------------------------

class PostgresAuditStore(AuditStore):
    """PostgreSQL/TimescaleDB audit trail for multi-replica deployments.
    Same method contract as SQLiteAuditStore (see interfaces.py)."""

    def __init__(self, dsn: str) -> None:
        import psycopg2  # lazy optional dependency
        self._psycopg2 = psycopg2
        self._dsn = dsn
        self._init_db()

    def _connect(self):
        return self._psycopg2.connect(self._dsn)

    def _init_db(self) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_log (
                    id              BIGSERIAL PRIMARY KEY,
                    ts              DOUBLE PRECISION NOT NULL,
                    container_id    TEXT NOT NULL,
                    container_name  TEXT NOT NULL,
                    pipeline        TEXT NOT NULL,
                    predicted_state TEXT NOT NULL,
                    confidence      REAL NOT NULL,
                    action          TEXT NOT NULL
                )
                """
            )
            cur.execute(
                'CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log (ts DESC)'
            )

    def log_action(self, container_id, container_name, pipeline,
                   predicted_state, confidence, action) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                '''INSERT INTO audit_log
                   (ts, container_id, container_name, pipeline,
                    predicted_state, confidence, action)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)''',
                (time.time(), container_id, container_name, pipeline,
                 predicted_state, confidence, action),
            )

    def recent_actions(self, limit: int = 50) -> list[dict]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                'SELECT id, ts, container_id, container_name, pipeline,'
                ' predicted_state, confidence, action'
                ' FROM audit_log ORDER BY ts DESC LIMIT %s',
                (limit,),
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def total_actions(self) -> int:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute('SELECT COUNT(*) FROM audit_log')
            return int(cur.fetchone()[0])

    def log_escalation(self, container_id, container_name, pipeline,
                       predicted_state, confidence) -> None:
        self.log_action(container_id, container_name, pipeline,
                        predicted_state, confidence, 'escalate')


class TimescaleMetricsStore:
    """Minimal TimescaleDB hypertable implementation of the metrics-store
    contract (write_tick / history). Used only when PULSE_METRICS_DSN or
    PULSE_DB_DSN is configured."""

    def __init__(self, dsn: str) -> None:
        import psycopg2
        self._psycopg2 = psycopg2
        self._dsn = dsn
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS metrics (
                    ts           DOUBLE PRECISION NOT NULL,
                    container_id TEXT NOT NULL,
                    cpu          REAL NOT NULL,
                    mem          REAL NOT NULL,
                    net          REAL NOT NULL
                )
                """
            )
            cur.execute(
                "SELECT create_hypertable('metrics', 'ts', if_not_exists => TRUE)"
            )

    def _connect(self):
        return self._psycopg2.connect(self._dsn)

    def write_tick(self, snapshots: list[dict]) -> None:
        now = time.time()
        with self._connect() as conn, conn.cursor() as cur:
            cur.executemany(
                'INSERT INTO metrics (ts, container_id, cpu, mem, net)'
                ' VALUES (%s, %s, %s, %s, %s)',
                [(now, s['id'], s['cpu'], s['mem'], s['net']) for s in snapshots],
            )

    def history(self, container_id: str, points: int = 120) -> list[dict]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                'SELECT time_bucket(%s, to_timestamp(ts)) AS bucket,'
                ' avg(cpu), avg(mem), avg(net) FROM metrics'
                ' WHERE container_id = %s GROUP BY bucket'
                ' ORDER BY bucket DESC LIMIT %s',
                (simulator.TICK_SECONDS, container_id, max(1, min(points, 1000))),
            )
            return [
                {'ts': b.timestamp(), 'cpu': c, 'mem': m, 'net': n}
                for b, c, m, n in reversed(cur.fetchall())
            ]


def make_audit_store() -> AuditStore:
    """Postgres when PULSE_DB_DSN is set and reachable, SQLite otherwise."""
    dsn = os.environ.get('PULSE_DB_DSN')
    if dsn:
        try:
            return PostgresAuditStore(dsn)
        except Exception:
            pass  # DB unreachable - never block the demo path
    return SQLiteAuditStore()


def make_metrics_store():
    """TimescaleDB when a DSN is configured and reachable, SQLite otherwise."""
    dsn = os.environ.get('PULSE_METRICS_DSN') or os.environ.get('PULSE_DB_DSN')
    if dsn:
        try:
            return TimescaleMetricsStore(dsn)
        except Exception:
            pass
    return SQLiteMetricsStore()
