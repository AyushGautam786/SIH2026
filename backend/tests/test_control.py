"""Control-layer tests: cooldown scoping/expiry, action choice, breaker."""
import control


def _cooldown_store():
    return control.InMemoryCooldownStore()


def test_cooldown_blocks_then_expires():
    store = _cooldown_store()
    cid, pid = "abc123", "checkout-service"
    assert not store.is_cooling_down(cid, pid)
    store.start_cooldown(cid, pid)
    assert store.is_cooling_down(cid, pid)
    assert 0 < store.seconds_left(cid, pid) <= control.COOLDOWN_SECONDS
    # Simulate TTL expiry by rewinding the stored expiry.
    key = ("checkout-service", "abc123")
    store._until[key] -= control.COOLDOWN_SECONDS + 1
    assert not store.is_cooling_down(cid, pid)
    assert store.seconds_left(cid, pid) == 0.0


def test_cooldown_is_pipeline_scoped():
    """One pipeline's cooldown must never suppress another pipeline's action."""
    store = _cooldown_store()
    store.start_cooldown("cid", "pipeline-a")
    assert store.is_cooling_down("cid", "pipeline-a")
    assert not store.is_cooling_down("cid", "pipeline-b")


def test_choose_action_memory_dominant_restarts():
    snap = {"mem": 88.0, "cpu": 60.0}
    assert control.choose_action(snap) == "restart"


def test_choose_action_cpu_dominant_scales():
    snap = {"mem": 40.0, "cpu": 92.0}
    assert control.choose_action(snap) == "scale"


def test_circuit_breaker_trips_at_max_actions():
    breaker = control.CircuitBreaker(max_actions=3, window_seconds=60)
    assert breaker.allow()
    for _ in range(3):
        breaker.record_action()
    assert not breaker.allow()
    assert breaker.state()["tripped"] is True


def test_circuit_breaker_recovers_after_window():
    breaker = control.CircuitBreaker(max_actions=2, window_seconds=60)
    breaker.record_action()
    breaker.record_action()
    assert not breaker.allow()
    # Age every event out of the sliding window.
    breaker._events.clear()
    assert breaker.allow()


def test_escalation_counter_increments():
    breaker = control.CircuitBreaker(max_actions=1, window_seconds=60)
    breaker.record_action()
    before = breaker.state()["total_escalations"]
    breaker.record_escalation()
    assert breaker.state()["total_escalations"] == before + 1
