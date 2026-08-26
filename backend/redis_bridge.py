"""
redis_bridge.py — Optional production-grade components backed by Redis.

Everything here degrades gracefully: if the `redis` package or a live Redis
server is unavailable, factories fall back to the prototype implementations,
so the demo always runs (ground rule #2 in TASKS.md).

Production behaviour (PPTX slides 5/9):
  - Cooldown keys are TTL-scoped per pipeline AND container:
        cooldown:{pipeline_id}:{container_id}   (SET ... EX <seconds>)
    so one pipeline's cooldown never suppresses another's remediation, and
    multiple backend replicas share the same guard state.
"""
import os

import control
from interfaces import CooldownStore
from registry import composite_key

REDIS_URL = os.environ.get("PULSE_REDIS_URL", "redis://localhost:6379/0")


class RedisCooldownStore(CooldownStore):
    """Redis-backed cooldown with TTL keys scoped per pipeline+container.
    Survives process restarts and is correct across multiple replicas."""

    def __init__(self, redis_client=None, url: str = REDIS_URL) -> None:
        if redis_client is None:
            import redis  # lazy optional dependency
            self.client = redis.Redis.from_url(url, decode_responses=True)
        else:
            self.client = redis_client

    @staticmethod
    def _key(container_id: str, pipeline_id: str | None = None) -> str:
        scope_pid, scope_cid = composite_key(pipeline_id, container_id)
        return f"cooldown:{scope_pid}:{scope_cid}"

    def is_cooling_down(self, container_id: str, pipeline_id: str | None = None) -> bool:
        return bool(self.client.exists(self._key(container_id, pipeline_id)))

    def start_cooldown(self, container_id: str, pipeline_id: str | None = None) -> None:
        self.client.set(self._key(container_id, pipeline_id), 1, ex=control.COOLDOWN_SECONDS)

    def seconds_left(self, container_id: str, pipeline_id: str | None = None) -> float:
        return float(self.client.ttl(self._key(container_id, pipeline_id)))


def make_cooldown_store(url: str | None = None) -> CooldownStore:
    """Redis store when reachable, prototype store otherwise."""
    try:
        store = RedisCooldownStore(url=url or REDIS_URL)
        store.client.ping()
        return store
    except Exception:
        return control.InMemoryCooldownStore()
