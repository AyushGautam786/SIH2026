#!/usr/bin/env python3
"""
pulse_agent.py - Pulse telemetry agent (Python reference implementation).

The production agent is agent/pulse_agent.cpp; this is the equivalent,
dependency-light reference used for development and demos:

  - collects per-container CPU / memory / network stats every 3 seconds,
  - tags each sample with the container's `pulse.pipeline` label,
  - emits one JSON line per container on stdout, or PUBLISHes them to Redis
    on the `pulse.telemetry` channel when REDIS_URL is set.

Usage:
    python pulse_agent.py                      # stdout stream
    REDIS_URL=redis://localhost:6379/0 python pulse_agent.py

Requires docker-py only when a Docker daemon is present; without it falls
back to printing an explanatory message and exiting cleanly (ground rule:
graceful degradation).
"""
import json
import os
import sys
import time

INTERVAL = int(os.environ.get("PULSE_INTERVAL_SECS", "3"))
REDIS_URL = os.environ.get("REDIS_URL")


def collect():
    """Yield one stats dict per running container."""
    import docker  # lazy optional dependency

    client = docker.from_env()
    while True:
        now = time.time()
        for container in client.containers.list():
            try:
                s = container.stats(stream=False)
            except Exception:
                continue

            cpu_delta = (
                s["cpu_stats"]["cpu_usage"]["total_usage"]
                - s.get("precpu_stats", {}).get("cpu_usage", {}).get("total_usage", 0)
            )
            sys_delta = (
                s["cpu_stats"].get("system_cpu_usage", 0)
                - s.get("precpu_stats", {}).get("system_cpu_usage", 0)
            )
            online = s["cpu_stats"].get("online_cpus", 1) or 1
            cpu_pct = 100.0 * cpu_delta / sys_delta * online if sys_delta > 0 else 0.0

            mem = s.get("memory_stats", {})
            nets = s.get("networks", {}) or {}
            rx = sum(n.get("rx_bytes", 0) for n in nets.values())
            tx = sum(n.get("tx_bytes", 0) for n in nets.values())

            labels = container.labels or {}
            yield {
                "ts": now,
                "container_id": container.short_id,
                "name": container.name,
                "pipeline_id": labels.get("pulse.pipeline", "default"),
                "cpu": round(cpu_pct, 2),
                "mem_used_mb": round(mem.get("usage", 0) / 1048576.0, 2),
                "mem_limit_mb": round(mem.get("limit", 0) / 1048576.0, 2),
                "net_rx_bps": rx,
                "net_tx_bps": tx,
            }
        time.sleep(INTERVAL)


def main():
    if REDIS_URL:
        try:
            import redis
            r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
            r.ping()
        except Exception as exc:
            print(f"[pulse_agent] Redis unavailable ({exc}); falling back to stdout",
                  file=sys.stderr)

    try:
        for sample in collect():
            line = json.dumps(sample)
            if REDIS_URL:
                try:
                    r.publish("pulse.telemetry", line)
                    continue
                except Exception:
                    pass  # Redis blip -> still print locally
            print(line, flush=True)
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        print(f"[pulse_agent] no Docker daemon reachable: {exc}", file=sys.stderr)
        print("[pulse_agent] start Docker Desktop, or run the backend's "
              "SimulatedFleet instead", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
