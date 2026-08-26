"""
simulator.py — Simulated container fleet (prototype TelemetrySource).

In the full Pulse architecture this data comes from lightweight C++ agents
polling the Docker socket on every host (see agent/pulse_agent.cpp). This
class implements the same TelemetrySource interface a real Docker-backed
implementation would, so swapping it out later (see interfaces.py) never
touches main.py or ml_model.py.

Telemetry per container (matches PPTX slide 12 "Captured Features"):
  - CPU utilisation %
  - Memory usage % + absolute MB against the container's memory limit (MB)
  - Disk read/write throughput (bytes/s)
  - Network RX/TX throughput (bytes/s) + aggregate load %
  - Active TCP connections
  - Packet drops per interval

Sampling cadence is 3 seconds (PPTX: "3-second polling interval"); the tick
interval itself lives in main.py — this module only produces samples.
"""
import random
import time
import uuid
from collections import deque
from dataclasses import dataclass, field

from interfaces import TelemetrySource

PIPELINES = ["checkout-service", "auth-service", "payments-worker"]
SCENARIOS = ["healthy", "spike", "at_risk"]

TICK_SECONDS = 3          # matches PPTX telemetry cadence
HISTORY_LEN = 120         # ~6 minutes of rolling window @3s ticks


@dataclass
class Container:
    id: str
    pipeline: str
    name: str
    cpu: float = 20.0                 # %
    mem: float = 30.0                 # %
    net: float = 50.0                 # aggregate load %
    mem_limit_mb: float = 512.0       # hard limit (cgroup style)
    disk_read_bps: float = 0.0        # bytes / s
    disk_write_bps: float = 0.0
    net_rx_bps: float = 0.0           # bytes / s
    net_tx_bps: float = 0.0
    tcp_connections: int = 12
    packet_drops: int = 0             # drops since last tick
    scenario: str = "healthy"
    scenario_ticks_left: int = 0
    history: deque = field(default_factory=lambda: deque(maxlen=HISTORY_LEN))
    last_action: str | None = None
    last_action_at: float | None = None

    def mem_used_mb(self) -> float:
        return round(self.mem / 100.0 * self.mem_limit_mb, 1)

    def snapshot(self) -> dict:
        return {
            "id": self.id,
            "pipeline": self.pipeline,
            "name": self.name,
            "cpu": round(self.cpu, 1),
            "mem": round(self.mem, 1),
            "net": round(self.net, 1),
            "mem_used_mb": self.mem_used_mb(),
            "mem_limit_mb": self.mem_limit_mb,
            "disk_read_bps": int(self.disk_read_bps),
            "disk_write_bps": int(self.disk_write_bps),
            "net_rx_bps": int(self.net_rx_bps),
            "net_tx_bps": int(self.net_tx_bps),
            "tcp_connections": int(self.tcp_connections),
            "packet_drops": int(self.packet_drops),
            "scenario": self.scenario,
            "last_action": self.last_action,
            "last_action_at": self.last_action_at,
        }

    def sample(self) -> dict:
        """One history entry — everything the feature extractor needs."""
        return {
            "t": time.time(),
            "cpu": self.cpu,
            "mem": self.mem,
            "net": self.net,
            "disk_read_bps": self.disk_read_bps,
            "disk_write_bps": self.disk_write_bps,
            "net_rx_bps": self.net_rx_bps,
            "net_tx_bps": self.net_tx_bps,
            "tcp_connections": self.tcp_connections,
        }


class SimulatedFleet(TelemetrySource):
    """Owns all simulated containers and advances their metrics each tick."""

    def __init__(self, n_containers: int = 6, pipelines: list[str] | None = None):
        self.containers: dict[str, Container] = {}
        pipes = pipelines or PIPELINES
        for i in range(n_containers):
            cid = str(uuid.uuid4())[:8]
            pipeline = pipes[i % len(pipes)]
            self.containers[cid] = Container(
                id=cid,
                pipeline=pipeline,
                name=f"{pipeline}-{i:02d}",
                mem_limit_mb=random.choice([256.0, 512.0, 1024.0]),
            )
        # Seed one history sample so features exist on the very first loop pass.
        self.tick()

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
        """Advance every container's metrics by one simulated timestep (3 s)."""
        for c in self.containers.values():
            if c.scenario_ticks_left <= 0 and c.scenario != "healthy":
                c.scenario = "healthy"

            if c.scenario == "healthy":
                targets = {"cpu": 20, "mem": 30, "net": 50, "disk": 0.4e6,
                           "rx": 2.5e6, "tx": 1.2e6, "tcp": 14, "drops": 0}
                jitter = 4
            elif c.scenario == "spike":
                targets = {"cpu": 78, "mem": 45, "net": 85, "disk": 2.2e6,
                           "rx": 9.5e6, "tx": 5.0e6, "tcp": 60, "drops": 2}
                jitter = 8
            else:  # at_risk — sustained, worsening load (leak-like behaviour)
                growth = max(0, 14 - c.scenario_ticks_left) * 2.5
                targets = {"cpu": 82 + growth, "mem": 75 + growth, "net": 70,
                           "disk": 3.5e6, "rx": 7.0e6, "tx": 3.8e6,
                           "tcp": 95 + growth * 2, "drops": 18}
                jitter = 5

            c.cpu = _drift(c.cpu, targets["cpu"], jitter)
            c.mem = _drift(c.mem, targets["mem"], jitter * 0.6)
            c.net = _drift(c.net, targets["net"], jitter)
            c.disk_read_bps = max(0.0, _drift(c.disk_read_bps, targets["disk"], targets["disk"] * 0.3))
            c.disk_write_bps = max(0.0, _drift(c.disk_write_bps, targets["disk"] * 0.6, targets["disk"] * 0.25))
            c.net_rx_bps = max(0.0, _drift(c.net_rx_bps, targets["rx"], targets["rx"] * 0.3))
            c.net_tx_bps = max(0.0, _drift(c.net_tx_bps, targets["tx"], targets["tx"] * 0.3))
            c.tcp_connections = max(0, int(_drift(float(c.tcp_connections), float(targets["tcp"]), 4.0)))
            c.packet_drops = max(0, int(random.gauss(targets["drops"], max(1.0, targets["drops"] * 0.35))))

            c.history.append(c.sample())
            if c.scenario_ticks_left > 0:
                c.scenario_ticks_left -= 1

    def recover(self, container_id: str) -> None:
        """Called by the control loop after a healing action succeeds."""
        c = self.containers.get(container_id)
        if c:
            c.scenario = "healthy"
            c.scenario_ticks_left = 0
            c.cpu, c.mem, c.net = 18.0, 28.0, 45.0
            c.disk_read_bps = c.disk_write_bps = 0.35e6
            c.net_rx_bps, c.net_tx_bps = 2.4e6, 1.1e6
            c.tcp_connections = 12
            c.packet_drops = 0

    def snapshot(self) -> list[dict]:
        return [c.snapshot() for c in self.containers.values()]


def _drift(current: float, target: float, jitter: float) -> float:
    """Move current value toward target with noise. Percentage-style values
    (both inputs <= 100) clamp to [0, 100]; byte-rate counters only clamp >= 0."""
    step = (target - current) * 0.35 + random.uniform(-jitter, jitter)
    if current <= 100.0 and target <= 100.0:
        return max(0.0, min(100.0, current + step))
    return current + step
