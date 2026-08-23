"""
control.py — Control-loop building blocks.

  - InMemoryCooldownStore: prototype CooldownStore implementation
  - SimulatedActionExecutor: prototype ActionExecutor implementation
  - choose_action(): pure decision logic, no infra dependency, used as-is
    in production too.

Swap InMemoryCooldownStore -> RedisCooldownStore and
SimulatedActionExecutor -> DockerActionExecutor in production
(see interfaces.py). Nothing else in main.py changes.
"""
import time

from interfaces import ActionExecutor, CooldownStore

COOLDOWN_SECONDS = 20


class InMemoryCooldownStore(CooldownStore):
    """Prototype cooldown store — an in-memory dict with expiry timestamps.
    Lost on process restart; fine for a single-process demo.
    Production: swap for RedisCooldownStore (a Redis key with EX TTL)."""

    def __init__(self) -> None:
        self._until: dict[str, float] = {}

    def is_cooling_down(self, container_id: str) -> bool:
        expiry = self._until.get(container_id)
        return expiry is not None and time.time() < expiry

    def start_cooldown(self, container_id: str) -> None:
        self._until[container_id] = time.time() + COOLDOWN_SECONDS

    def seconds_left(self, container_id: str) -> float:
        expiry = self._until.get(container_id, 0.0)
        return max(0.0, expiry - time.time())


class SimulatedActionExecutor(ActionExecutor):
    """Prototype executor — flips the simulated container back to healthy.
    Production version calls the real Docker/Kubernetes API instead;
    see DockerActionExecutor stub in the migration guide."""

    def __init__(self, fleet) -> None:
        # fleet is any TelemetrySource that exposes .recover(id)
        self.fleet = fleet

    def execute(self, container_id: str, action: str) -> bool:
        self.fleet.recover(container_id)
        return True


def choose_action(container_snapshot: dict) -> str:
    """Pick restart vs scale based on which resource is the problem.

    Pure function, no infra dependency — used unchanged in production.
      - Memory-dominant? -> restart (clears leak-like memory growth)
      - CPU-dominant?    -> scale  (add capacity for sustained CPU load)
    """
    if container_snapshot["mem"] >= container_snapshot["cpu"]:
        return "restart"
    return "scale"
