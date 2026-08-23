"""
simulator.py — Simulated container fleet (prototype TelemetrySource).

In the full Pulse architecture, this data comes from lightweight C++ agents
polling the Docker socket on every host. This class implements the same
TelemetrySource interface a real Docker-backed implementation would, so
swapping this out later (see interfaces.py) doesn't touch main.py or
ml_model.py at all.
"""
import random
import time
import uuid
from collections import deque
from dataclasses import dataclass, field

from interfaces import TelemetrySource

PIPELINES = ["checkout-service", "auth-service", "payments-worker"]
SCENARIOS = ["healthy", "spike", "at_risk"]


@dataclass
class Container:
    id: str
    pipeline: str
    name: str
    cpu: float = 20.0
    mem: float = 30.0
    net: float = 50.0
    scenario: str = "healthy"
    scenario_ticks_left: int = 0
    history: deque = field(default_factory=lambda: deque(maxlen=12))
    last_action: str | None = None
    last_action_at: float | None = None

    def snapshot(self) -> dict:
        return {
            "id": self.id,
            "pipeline": self.pipeline,
            "name": self.name,
            "cpu": round(self.cpu, 1),
            "mem": round(self.mem, 1),
            "net": round(self.net, 1),
            "scenario": self.scenario,
            "last_action": self.last_action,
            "last_action_at": self.last_action_at,
        }


class SimulatedFleet(TelemetrySource):
    """Owns all simulated containers and advances their metrics each tick."""

    def __init__(self, n_containers: int = 6):
        self.containers: dict[str, Container] = {}
        for i in range(n_containers):
            cid = str(uuid.uuid4())[:8]
            pipeline = PIPELINES[i % len(PIPELINES)]
            self.containers[cid] = Container(
                id=cid,
                pipeline=pipeline,
                name=f"{pipeline}-{i:02d}",
            )

    def inject_scenario(self, container_id: str, scenario: str) -> bool:
        """Manually trigger a spike / at-risk episode — used by the demo UI
        so you can show the detect → predict → heal loop live."""
        c = self.containers.get(container_id)
        if not c or scenario not in SCENARIOS:
            return False
        c.scenario = scenario
        c.scenario_ticks_left = 8 if scenario == "spike" else 14
        return True

    def tick(self) -> None:
        """Advance every container's metrics by one simulated timestep."""
        for c in self.containers.values():
            if c.scenario_ticks_left <= 0 and c.scenario != "healthy":
                c.scenario = "healthy"

            if c.scenario == "healthy":
                target_cpu, target_mem, target_net = 20, 30, 50
                jitter = 4
            elif c.scenario == "spike":
                target_cpu, target_mem, target_net = 78, 45, 85
                jitter = 8
            else:  # at_risk — sustained, worsening load
                growth = max(0, 14 - c.scenario_ticks_left) * 2.5
                target_cpu = 82 + growth
                target_mem = 75 + growth
                target_net = 70
                jitter = 5

            c.cpu = _drift(c.cpu, target_cpu, jitter)
            c.mem = _drift(c.mem, target_mem, jitter * 0.6)
            c.net = _drift(c.net, target_net, jitter)

            c.history.append({"t": time.time(), "cpu": c.cpu, "mem": c.mem, "net": c.net})
            if c.scenario_ticks_left > 0:
                c.scenario_ticks_left -= 1

    def recover(self, container_id: str) -> None:
        """Called by the control loop after a healing action succeeds."""
        c = self.containers.get(container_id)
        if c:
            c.scenario = "healthy"
            c.scenario_ticks_left = 0
            c.cpu, c.mem, c.net = 18.0, 28.0, 45.0

    def snapshot(self) -> list[dict]:
        return [c.snapshot() for c in self.containers.values()]


def _drift(current: float, target: float, jitter: float) -> float:
    """Move current value toward target with noise, clamped to [0, 100]."""
    step = (target - current) * 0.35 + random.uniform(-jitter, jitter)
    return max(0.0, min(100.0, current + step))
