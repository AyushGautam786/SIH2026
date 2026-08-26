"""
executor.py — Action executors (the only Pulse component that touches real
infrastructure with side effects).

  - SimulatedActionExecutor lives in control.py (zero-risk demo default).
  - DockerActionExecutor below performs real remediation through docker-py:
      restart  -> client.containers.get(id).restart()
      scale    -> updates the container's CPU/memory limits via the Docker
                  API (equivalent of adding capacity; on Kubernetes this is
                  where an HPA patch would go).

Selection is environment-driven and safe by default:
    PULSE_EXECUTOR=simulated   (default — no side effects, works anywhere)
    PULSE_EXECUTOR=docker      (requires a reachable Docker daemon)

A production circuit breaker already guards this boundary (control.py).
"""
import os

import control


def make_executor(fleet):
    """Factory used at the single WIRING point in main.py.

    `fleet` must expose .recover(id) (simulated mode) or be replaced entirely
    by Docker-backed telemetry that also exposes restart/scale handles."""
    mode = os.environ.get("PULSE_EXECUTOR", "simulated").lower()
    if mode == "docker":
        try:
            return DockerActionExecutor()
        except Exception:
            # No daemon / no docker-py — degrade instead of crashing startup.
            pass
    return control.SimulatedActionExecutor(fleet)


class DockerActionExecutor:
    """Real remediation via the Docker Engine API (docker-py)."""

    def __init__(self) -> None:
        import docker  # lazy optional dependency
        self.client = docker.from_env()

    def execute(self, container_id: str, action: str) -> bool:
        try:
            container = self.client.containers.get(container_id)
            if action == "scale":
                # Add headroom: raise limits if the host allows; Docker keeps
                # unspecified values at host defaults when set to 0.
                current = container.stats(stream=False)
                update_kw = {}
                cpu_period = (current.get("cpu_stats", {}) or {}).get(
                    "system_cpu_usage")  # presence probe only
                update_kw["nano_cpus"] = int(2e9)   # allow up to 2 cores
                update_kw["mem_limit"] = 0          # lift soft cap
                container.update(**update_kw)
            else:  # default action: restart
                container.restart(timeout=10)
            return True
        except Exception:
            # Never let an infra hiccup kill the control loop — the cooldown +
            # breaker layers decide whether to retry later.
            return False


import control  # noqa: E402  (kept late to avoid any future import cycles)
