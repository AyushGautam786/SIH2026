"""Fleet-scale hardening test (PPTX slide 14: 'concurrency tests with 100+
active pipelines').

Runs the real detect -> predict -> heal logic over a 120-pipeline / 360-
container fleet WITHOUT a server or database, asserting:

  1. per-tick latency stays within budget,
  2. the circuit breaker trips under mass failure injection instead of
     firing hundreds of restarts,
  3. cooldown scoping holds (no cross-pipeline suppression).

Run:  cd backend && python -m tests.stress_test
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import control                                    # noqa: E402
import ml_model                                   # noqa: E402
from simulator import SimulatedFleet              # noqa: E402

PIPELINES = 120
CONTAINERS = PIPELINES * 3          # 3 replicas each -> 360 containers
TICKS = 20
LATENCY_BUDGET_S = 5.0              # generous CI ceiling per tick


class ListAudit:
    """Test double for the audit store contract."""

    def __init__(self):
        self.rows = []

    def log_action(self, cid, name, pipeline, state, conf, action):
        self.rows.append((cid, action))

    def log_escalation(self, cid, name, pipeline, state, conf):
        self.rows.append((cid, "escalate"))

    def total_actions(self):
        return len(self.rows)


def main() -> int:
    pipelines = [f"pipeline-{i:03d}" for i in range(PIPELINES)]
    fleet = SimulatedFleet(n_containers=CONTAINERS, pipelines=pipelines)
    guard = control.InMemoryCooldownStore()
    breaker = control.CircuitBreaker()
    throttle = control.EscalationThrottle()
    audit = ListAudit()

    print(f"[stress] fleet: {len(fleet.containers)} containers "
          f"across {len(pipelines)} pipelines; {TICKS} ticks")

    # Warm-up ticks so features exist.
    for _ in range(2):
        fleet.tick()

    latencies = []
    actions = 0
    escalations = 0
    for tick in range(TICKS):
        if tick == TICKS // 3:
            # Mass failure: inject at_risk into EVERY container at once —
            # worst-case systemic event the breaker exists for.
            for cid in fleet.containers:
                fleet.inject_scenario(cid, "at_risk")
            print("[stress] injected at_risk into every container")

        start = time.perf_counter()
        fleet.tick()  # DETECT

        containers = list(fleet.containers.values())
        predictions = ml_model.predict_batch(
            [list(c.history) for c in containers]  # PREDICT (batched)
        )

        for c, (state, confidence) in zip(containers, predictions):
            if state != "at_risk":
                continue
            if guard.is_cooling_down(c.id, c.pipeline):
                continue
            if not breaker.allow():
                if throttle.should_log(c.id):
                    breaker.record_escalation()
                    audit.log_escalation(c.id, c.name, c.pipeline, state, confidence)
                continue
            action = control.choose_action(c.snapshot())
            executor_ok = fleet.recover(c.id) is None      # HEAL (simulated)
            if executor_ok:
                guard.start_cooldown(c.id, c.pipeline)
                breaker.record_action()
                c.last_action = action
                audit.log_action(c.id, c.name, c.pipeline, state, confidence, action)

        elapsed = time.perf_counter() - start
        latencies.append(elapsed)
        assert elapsed < LATENCY_BUDGET_S, \
            f"tick {tick} blew the latency budget: {elapsed:.2f}s"

    actions = sum(1 for _, a in audit.rows if a in ("restart", "scale"))
    escalations = sum(1 for _, a in audit.rows if a == "escalate")

    # ---- invariants -------------------------------------------------------
    peak_latency = max(latencies)
    avg_latency = sum(latencies) / len(latencies)

    assert actions > 0, "healing never fired even before mass failure"
    assert escalations > 0, (
        "circuit breaker never tripped under mass failure - anti-thrashing broken"
    )
    assert actions < len(fleet.containers), (
        f"{actions} actions for {len(fleet.containers)} containers: "
        "breaker should have suppressed most"
    )

    # Cooldown scoping sanity: a cooled container in one pipeline must not
    # cool its same-named replica in another pipeline.
    sample_cid = next(iter(fleet.containers))
    other_pid = next(p for p in pipelines
                     if p != fleet.containers[sample_cid].pipeline)
    assert not guard.is_cooling_down(sample_cid, other_pid)

    print(f"[stress] avg tick latency : {avg_latency * 1000:8.1f} ms")
    print(f"[stress] peak tick latency: {peak_latency * 1000:8.1f} ms")
    print(f"[stress] healing actions  : {actions}")
    print(f"[stress] escalations      : {escalations}")
    print("[stress] PASS: latency within budget, breaker held, scoping intact")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
