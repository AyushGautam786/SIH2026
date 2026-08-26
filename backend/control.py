"""
control.py — Control-loop building blocks.

  - InMemoryCooldownStore: prototype CooldownStore implementation
    (scoped per pipeline+container like the production Redis version)
  - CircuitBreaker: fleet-scale anti-thrashing guard (PPTX slide 9) —
    refuses autonomous action when too many have fired recently and
    asks the loop to escalate to a human instead
  - SimulatedActionExecutor: prototype ActionExecutor implementation
  - choose_action(): pure decision logic, no infra dependency, used as-is
    in production too.

Swap InMemoryCooldownStore -> RedisCooldownStore (redis_bridge.py) and
SimulatedActionExecutor -> DockerActionExecutor (executor.py) in production.
Nothing else in main.py changes.
"""
import time
from collections import deque

from interfaces import ActionExecutor, CooldownStore
from registry import composite_key

COOLDOWN_SECONDS = 20

# Circuit-breaker defaults (PPTX slide 9 "Anti-Thrashing").
BREAKER_WINDOW_SECONDS = 60
BREAKER_MAX_ACTIONS = 6


class InMemoryCooldownStore(CooldownStore):
    """Prototype cooldown store — an in-memory dict with expiry timestamps,
    keyed by (pipeline_id, container_id) exactly like the production Redis
    key `cooldown:{pipeline_id}:{container_id}`, so scoping semantics are
    identical between prototype and production."""

    def __init__(self) -> None:
        self._until: dict[tuple[str, str], float] = {}

    def _key(self, container_id: str, pipeline_id: str | None = None):
        return composite_key(pipeline_id, container_id)

    def is_cooling_down(self, container_id: str, pipeline_id: str | None = None) -> bool:
        expiry = self._until.get(self._key(container_id, pipeline_id))
        return expiry is not None and time.time() < expiry

    def start_cooldown(self, container_id: str, pipeline_id: str | None = None) -> None:
        self._until[self._key(container_id, pipeline_id)] = time.time() + COOLDOWN_SECONDS

    def seconds_left(self, container_id: str, pipeline_id: str | None = None) -> float:
        expiry = self._until.get(self._key(container_id, pipeline_id), 0.0)
        return max(0.0, expiry - time.time())


class SimulatedActionExecutor(ActionExecutor):
    """Prototype executor — flips the simulated container back to healthy.
    Production version calls the real Docker/Kubernetes API instead;
    see DockerActionExecutor in executor.py."""

    def __init__(self, fleet) -> None:
        # fleet is any TelemetrySource that exposes .recover(id)
        self.fleet = fleet

    def execute(self, container_id: str, action: str) -> bool:
        self.fleet.recover(container_id)
        return True


class EscalationThrottle:
    """At most one ESCALATION row per container per interval, even while the
    breaker stays tripped across many ticks — keeps the audit trail readable
    (one 'needs human' event per container per window, not one per tick)."""

    def __init__(self, interval: float = COOLDOWN_SECONDS) -> None:
        self.interval = interval
        self._last: dict[str, float] = {}

    def should_log(self, container_id: str) -> bool:
        now = time.time()
        if now - self._last.get(container_id, 0.0) >= self.interval:
            self._last[container_id] = now
            return True
        return False

    def state(self) -> dict:
        return {"interval_seconds": self.interval, "tracked": len(self._last)}


class CircuitBreaker:
    """Fleet-scale anti-thrashing guard (PPTX slide 9).

    Even with per-container cooldowns, a systemic event (bad deploy rolling
    through every pipeline) could fire many restarts at once and amplify an
    outage. The breaker tracks autonomous actions in a sliding window; once
    BREAKER_MAX_ACTIONS have fired within BREAKER_WINDOW_SECONDS it trips and
    `allow()` returns False until old actions age out of the window. While
    tripped, the control loop logs an ESCALATION instead of acting.
    """

    def __init__(self, max_actions: int = BREAKER_MAX_ACTIONS,
                 window_seconds: float = BREAKER_WINDOW_SECONDS) -> None:
        self.max_actions = max_actions
        self.window_seconds = window_seconds
        self._events: deque[float] = deque()
        self.escalations = 0

    def allow(self) -> bool:
        self._prune()
        return len(self._events) < self.max_actions

    def record_action(self) -> None:
        now = time.time()
        self._events.append(now)
        self._prune(now)

    def record_escalation(self) -> None:
        self.escalations += 1

    def _prune(self, now: float | None = None) -> None:
        now = now if now is not None else time.time()
        cutoff = now - self.window_seconds
        while self._events and self._events[0] < cutoff:
            self._events.popleft()

    def state(self) -> dict:
        """Payload for GET /api/config + dashboard safety widget."""
        self._prune()
        return {
            "tripped": not self.allow(),
            "actions_in_window": len(self._events),
            "max_actions": self.max_actions,
            "window_seconds": self.window_seconds,
            "total_escalations": self.escalations,
        }


def choose_action(container_snapshot: dict) -> str:
    """Pick restart vs scale based on which resource is the problem.

    Pure function, no infra dependency — used unchanged in production.
      - Memory-dominant? -> restart (clears leak-like memory growth)
      - CPU-dominant?    -> scale  (add capacity for sustained CPU load)
    """
    if container_snapshot["mem"] >= container_snapshot["cpu"]:
        return "restart"
    return "scale"
