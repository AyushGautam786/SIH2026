# Pulse Telemetry Agents

Lightweight collectors that read live container statistics off the Docker
Engine API and feed the Pulse control engine. Two implementations of the
same contract:

| File | Role | Dependencies |
|---|---|---|
| `pulse_agent.cpp` | Production path - C++17, near-zero overhead (PPTX: ~2 MB RSS, <0.5% CPU) | none (POSIX sockets) |
| `pulse_agent.py` | Development/reference agent | `docker` (docker-py), optional `redis` |

## Contract

Every `PULSE_INTERVAL_SECS` (default **3**, matching the PPTX telemetry
cadence) each agent emits **one JSON line per container**:

```json
{"ts": 1724432400.1,
 "container_id": "a1b2c3d4e5f6",
 "name": "checkout-service-00",
 "pipeline_id": "checkout-service",
 "cpu": 82.4,
 "mem_used_mb": 412.5,
 "mem_limit_mb": 512.0,
 "net_rx_bps": 2500000,
 "net_tx_bps": 1200000}
```

Output sink:

1. **stdout** (one JSON object per line) - pipe it anywhere.
2. **Redis Pub/Sub** on channel `pulse.telemetry` when configured:
   - C++ agent: set `PULSE_REDIS_HOST` (+ optional `PULSE_REDIS_PORT`)
   - Python agent: set `REDIS_URL=redis://host:6379/0`

## Pipeline tagging

Tag containers at launch; the agent attaches the tag to every sample so the
control engine can scope state/cooldowns/actions per pipeline:

```bash
docker run -l pulse.pipeline=checkout-service your-image
```

Untagged containers fall under the `default` pipeline scope.

## Building & running the C++ agent (Linux host with Docker)

```bash
g++ -std=c++17 -O2 -o pulse_agent pulse_agent.cpp
sudo ./pulse_agent                       # reads /var/run/docker.sock directly
sudo PULSE_REDIS_HOST=127.0.0.1 ./pulse_agent   # + publish to Redis
```

> The C++ agent targets Linux/Docker hosts and is **not** built on Windows
> dev machines; the Python agent (`python pulse_agent.py`) covers Windows
> development against Docker Desktop.

## Feeding the backend

The backend consumes `pulse.telemetry` through its telemetry-source swap
point (`interfaces.py -> TelemetrySource`). Point a `RedisTelemetrySource`
implementation at the channel and change one wiring line in `backend/main.py`
- the detect -> predict -> heal loop never changes.
