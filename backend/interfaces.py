"""
interfaces.py — Abstract contracts for every piece of Pulse that is
"simulated" in the prototype and "real infrastructure" in production.

The rule this file enforces: main.py and ml_model.py NEVER import a
concrete class directly. They only ever talk to these four abstract
contracts. Upgrading Pulse from prototype to production is:

    1. Write a new class that implements the interface below.
    2. Change ONE line in main.py's wiring section.
    3. Nothing else in the codebase changes.

Each interface documents both what the prototype's implementation does
AND what the production implementation must do — this file doubles as
the spec for the upgrade work.
"""
from abc import ABC, abstractmethod


class TelemetrySource(ABC):
    """
    Where container metrics come from.

    PROTOTYPE implementation: SimulatedFleet (simulator.py) — generates
    synthetic CPU/mem/net numbers in-process, with an inject_scenario()
    hook for demos.

    PRODUCTION implementation: DockerTelemetrySource — polls the real
    Docker Engine API (container.stats()) on a fixed interval across every
    host, normalizes readings into the same dict shape, and publishes them
    via Redis Pub/Sub if multi-host. See the migration guide for a full stub.
    """

    @abstractmethod
    def tick(self) -> None:
        """Advance all containers by one timestep (prototype) or poll live
        stats for this interval (production)."""
        raise NotImplementedError

    @abstractmethod
    def snapshot(self) -> list[dict]:
        """Return current state of every container. Each dict MUST contain
        at minimum: id, pipeline, name, cpu, mem, net, history
        (list of recent {t, cpu, mem, net} readings, used for feature
        extraction in ml_model.py)."""
        raise NotImplementedError


class CooldownStore(ABC):
    """
    Tracks which containers are in a post-action cooldown window, so a
    restart's own CPU blip can't immediately re-trigger another restart.

    PROTOTYPE implementation: InMemoryCooldownStore — a dict with expiry
    timestamps. Lost on process restart; fine for a single-process demo.

    PRODUCTION implementation: RedisCooldownStore — a Redis key per
    container with `SET key 1 EX <seconds>`. Survives process restarts,
    and works correctly across multiple backend replicas (which an
    in-memory dict cannot do).
    """

    @abstractmethod
    def is_cooling_down(self, container_id: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def start_cooldown(self, container_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def seconds_left(self, container_id: str) -> float:
        raise NotImplementedError


class AuditStore(ABC):
    """
    Permanent, queryable record of every autonomous action Pulse has taken.
    This is the trust layer — it must survive restarts and be queryable by
    time range, container, and pipeline for post-incident review.

    PROTOTYPE implementation: SQLiteAuditStore — a local .db file, zero
    setup, single-writer.

    PRODUCTION implementation: PostgresAuditStore (ideally on TimescaleDB) —
    same two methods, backed by a real time-series-friendly table, safe for
    concurrent writers, and connectable from the dashboard for historical
    queries.
    """

    @abstractmethod
    def log_action(
        self,
        container_id: str,
        container_name: str,
        pipeline: str,
        predicted_state: str,
        confidence: float,
        action: str,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def recent_actions(self, limit: int = 50) -> list[dict]:
        raise NotImplementedError


class ActionExecutor(ABC):
    """
    Actually performs a healing action on a container. This is the
    highest-stakes swap point — it's the only interface that touches real
    infrastructure with side effects.

    PROTOTYPE implementation: SimulatedActionExecutor — flips the simulated
    container back to a healthy state, purely in-process.

    PRODUCTION implementation: DockerActionExecutor (or a Kubernetes-native
    equivalent hooking into the Horizontal Pod Autoscaler) — calls the real
    container.restart() / scale API. This is also where a circuit breaker
    belongs: refuse to act if too many actions have already fired fleet-wide
    in the last N seconds, and escalate to a human instead.
    """

    @abstractmethod
    def execute(self, container_id: str, action: str) -> bool:
        """Perform `action` ("restart" or "scale") on `container_id`.
        Returns True if the action was carried out."""
        raise NotImplementedError
