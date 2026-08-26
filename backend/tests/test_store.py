"""Storage tests: audit roundtrip, escalation rows, metrics time-series."""
import store


def test_audit_roundtrip(tmp_path):
    db = tmp_path / "audit.db"
    s = store.SQLiteAuditStore(db_path=db)
    s.log_action("cid", "web-01", "checkout-service", "at_risk", 0.94, "restart")
    rows = s.recent_actions(limit=10)
    assert len(rows) == 1
    row = rows[0]
    assert row["container_id"] == "cid"
    assert row["action"] == "restart"
    assert abs(row["confidence"] - 0.94) < 1e-6
    assert s.total_actions() == 1


def test_escalation_logged_as_action(tmp_path):
    s = store.SQLiteAuditStore(db_path=tmp_path / "audit.db")
    s.log_escalation("cid", "web-01", "auth-service", "at_risk", 0.91)
    rows = s.recent_actions()
    assert rows[0]["action"] == "escalate"
    assert rows[0]["pipeline"] == "auth-service"


def test_metrics_roundtrip_and_order(tmp_path):
    m = store.SQLiteMetricsStore(db_path=tmp_path / "metrics.db")
    m.write_tick([{"id": "c1", "cpu": 10.0, "mem": 20.0, "net": 30.0}])
    m.write_tick([{"id": "c1", "cpu": 15.0, "mem": 25.0, "net": 35.0}])
    hist = m.history("c1", points=10)
    assert len(hist) == 2
    # Oldest first (chronological order for charting).
    assert hist[0]["cpu"] == 10.0 and hist[-1]["cpu"] == 15.0


def test_metrics_isolated_per_container(tmp_path):
    m = store.SQLiteMetricsStore(db_path=tmp_path / "metrics.db")
    m.write_tick([
        {"id": "a", "cpu": 1.0, "mem": 2.0, "net": 3.0},
        {"id": "b", "cpu": 9.0, "mem": 8.0, "net": 7.0},
    ])
    assert m.history("a")[0]["cpu"] == 1.0
    assert m.history("b")[0]["cpu"] == 9.0


def test_factories_default_to_sqlite():
    assert isinstance(store.make_metrics_store(), store.SQLiteMetricsStore)
