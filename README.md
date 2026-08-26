# Pulse ⬡ — Predictive Self-Healing Container Monitor

> **Detect → Predict → Heal** — autonomously, with a 3-class ML classifier at its core.

Pulse is a real-time container fleet monitoring system that goes beyond simple threshold alerts. It uses a trained **RandomForestClassifier** to distinguish between three container states, and automatically heals containers that are truly at risk — without human intervention.

---

## ✨ What makes Pulse different

| Approach | Pulse | Simple threshold alarm |
|---|---|---|
| Distinguishes burst vs. sustained load | ✅ 3-class ML model | ❌ single threshold |
| Autonomous healing | ✅ RESTART or SCALE chosen per container | ❌ just alerts |
| Cooldown guard | ✅ prevents restart loops | ❌ can re-trigger |
| Tamper-evident audit trail | ✅ every decision logged | ❌ no record |
| Upgrade path to production | ✅ 4 clear interface swap-points | ❌ tightly coupled |

---

## 🏗 Project Structure

```
pulse/
├── TASKS.md                         # Master task list / agent continuity doc
├── docker-compose.yml               # redis + timescale + backend + frontend
├── .env.example                     # Optional production env vars
│
├── backend/                         # Python / FastAPI control engine
│   ├── requirements.txt
│   ├── main.py                      # Wiring + detect-predict-heal loop (3s ticks)
│   ├── interfaces.py                # Abstract contracts for the swap-points
│   ├── registry.py                  # Pipeline Registry (pipeline isolation)
│   ├── simulator.py                 # SimulatedFleet: CPU/mem/net/disk/RX-TX/TCP/drops
│   ├── ml_model.py                  # Random Forest, 8-feature vector, joblib persist
│   ├── control.py                   # Cooldowns + CircuitBreaker + EscalationThrottle
│   ├── redis_bridge.py              # Redis TTL cooldown (graceful fallback)
│   ├── executor.py                  # Simulated | Docker action executors
│   ├── store.py                     # SQLite/Postgres audit + SQLite/Timescale metrics
│   └── tests/
│       ├── test_ml.py               # Feature contract + accuracy >0.95
│       ├── test_control.py          # Cooldown scoping, breaker trip/recover
│       ├── test_store.py            # Audit + metrics roundtrips
│       ├── test_registry.py         # Pipeline scoping + worst-state rollups
│       └── stress_test.py           # 120 pipelines / 360 containers hardening
│
├── agent/                           # Production telemetry path (PPTX layer 1)
│   ├── pulse_agent.cpp              # C++17 Docker-socket agent (zero deps)
│   ├── pulse_agent.py               # Python reference agent
│   └── README.md                    # Build/run instructions
│
└── frontend/                        # React + Vite dashboard (no chart libs)
    ├── Dockerfile / nginx.conf      # nginx serving dist, proxies /api + /ws
    └── src/
        ├── App.jsx                  # Landing page + tabbed workspace
        ├── lib/api.js               # WS/REST client + fleet helpers
        └── components/
            ├── PipelineGroup.jsx    # Fleet grouped by pipeline (worst-state)
            ├── TopologyGraph.jsx    # SVG pipeline→container topology map
            ├── ContainerCard.jsx    # Per-container card with metric bars
            ├── ContainerDetail.jsx  # Drill-down drawer w/ live charts + features
            ├── MetricChart.jsx      # SVG sparkline/area charts
            └── AuditLog.jsx         # Scrolling autonomous action log
```

---

## 🚀 Quick Start

### 1. Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

The server starts at **http://localhost:8000**. The ML model trains automatically on first import (takes ~1 second on CPU).

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173** in your browser. The dashboard connects to the backend over WebSocket automatically.

---

## 🔬 The ML Model

The classifier is a `RandomForestClassifier` (150 trees, depth 8). It trains
once on a synthetic incident corpus shaped like the simulator's scenarios and
persists to `backend/models/rf_model.joblib` — subsequent startups load the
offline-trained artifact instantly (PPTX slide 10: trained offline, loaded for
live inference).

It distinguishes three states:

| Class | Meaning | Response |
|---|---|---|
| `healthy` | Normal load pattern | none |
| `transient_spike` | Harmless burst — high *now*, low rolling avg | ignored |
| `at_risk` | Sustained/worsening — includes pre-failure precursors | heal |

**Feature vector** (8 features, PPTX slides 10/13):

```
cpu           latest CPU %
mem           latest memory %
net           latest network load %
cpu_avg_1m    rolling mean CPU ~1 min   → bursts vs sustained
cpu_avg_5m    rolling mean CPU ~5 min   → slow failure ramps
mem_delta_30s memory change ~30 s       → leak detection
net_std_1m    network volatility ~1 min → erratic traffic
cpu_mem_ratio CPU/MEM imbalance         → maxed-CPU/idle-RAM anomalies
```

**Predictive labeling**: part of the `at_risk` training class comes from the
~3-minute window preceding a simulated crash (readings still mid-range, trend
already climbing) so Pulse acts on failure *precursors*, not just failures.

Fleet-scale hot path: `predict_batch()` classifies the entire fleet in ONE
forest pass per tick (360 containers ≈ 20 ms end-to-end — see stress test).

---

## 🔄 Architecture: Built to be replaced

Every piece of infrastructure this prototype simulates sits behind a formal interface in `interfaces.py`. `main.py` **never** talks to a concrete class directly — only to these four contracts:

| Interface | Prototype impl | Production impl |
|---|---|---|
| `TelemetrySource` | `SimulatedFleet` | `DockerTelemetrySource` |
| `CooldownStore` | `InMemoryCooldownStore` | `RedisCooldownStore` |
| `AuditStore` | `SQLiteAuditStore` | `PostgresAuditStore` |
| `ActionExecutor` | `SimulatedActionExecutor` | `DockerActionExecutor` |

**Upgrading any piece** = write a class implementing the interface, change one constructor call in `main.py`'s wiring section. The detect-predict-heal loop itself never changes.

---

## 🌐 API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | Liveness check |
| `GET` | `/api/containers` | Current snapshot of all containers |
| `GET` | `/api/audit?limit=50` | Recent autonomous actions (most recent first) |
| `GET` | `/api/stats` | Aggregated fleet stats (pipelines, at-risk, actions, breaker) |
| `GET` | `/api/pipelines` | Pipeline rollup — status = worst container state |
| `GET` | `/api/history/{container_id}?points=120` | Time-series metrics (charts) |
| `GET` | `/api/model/info` | Feature list, importances, artifact path |
| `GET` | `/api/config` | Runtime config + safety-layer status |
| `POST` | `/api/inject/{container_id}/{spike\|at_risk}` | Demo: inject a scenario |
| `WS` | `/ws` | Live tick stream pushed every 3 seconds |

### WebSocket message format

```json
{
  "type": "tick",
  "ts": 1724432400.123,
  "containers": [
    {
      "id": "a1b2c3d4",
      "name": "checkout-service-00",
      "pipeline": "checkout-service",
      "cpu": 82.3,
      "mem": 77.1,
      "net": 64.5,
      "predicted_state": "at_risk",
      "confidence": 0.94,
      "cooldown_seconds_left": 0.0,
      "action_taken": "restart"
    }
  ]
}
```

---

## 🎬 Demo Guide

1. **Observe the fleet** — six simulated containers across three pipelines, streaming live CPU/mem/net/disk/RX-TX/TCP every 3 seconds.

2. **Click "🔥 Inject At-Risk"** on any card:
   - Watch the badge flip to `AT RISK`
   - Within 1–2 ticks an entry appears in the Autonomous Action Log (`RESTART` or `SCALE`)
   - The card recovers to `HEALTHY` on its own — no human involved

3. **Click "⚡ Inject Spike"** on another card:
   - Badge flips to `SPIKE` (orange)
   - **No** action is logged — the model correctly identifies it as a harmless burst
   - Card recovers automatically after 8 ticks

4. **Show the audit log** — every autonomous decision is recorded with timestamp, container, pipeline, action, and model confidence. This is the trust layer.

---

## 🗺 What's Real vs. Simulated

| Component | Prototype | Production |
|---|---|---|
| Telemetry | Synthetic metrics in-process | C++ agents polling Docker socket per host |
| Message bus | In-memory function calls | Redis Pub/Sub fan-in across hosts |
| ML model | Real RandomForest on synthetic data | Same model trained on real Prometheus/cAdvisor history |
| Cooldown guard | In-memory dict with expiry | Redis key with TTL |
| Audit log | SQLite local file | PostgreSQL / TimescaleDB |
| Dashboard | React + Vite + WebSocket | Same (this code is already production-ready) |
| Action executor | In-process fleet state flip | Real `container.restart()` / HPA scale API |

---

## 📦 Dependencies

### Backend
```
fastapi==0.115.0
uvicorn[standard]==0.30.6
scikit-learn==1.5.1
numpy==1.26.4
websockets==13.0
```

### Frontend
```
react ^19
react-dom ^19
vite ^6
```

---

## 🔮 Production Upgrade Path

1. **Telemetry**: Implement `DockerTelemetrySource(TelemetrySource)` using `docker-py`'s `container.stats()` stream. Publish to Redis Pub/Sub per host. The loop in `main.py` never changes.

2. **Cooldown**: Implement `RedisCooldownStore(CooldownStore)` using `redis-py` with `SET key 1 EX 20`. Handles multiple backend replicas correctly.

3. **Audit**: Implement `PostgresAuditStore(AuditStore)` using `asyncpg`. Ideally on TimescaleDB for time-series compression and fast range queries.

4. **Executor**: Implement `DockerActionExecutor(ActionExecutor)` calling `container.restart()` or the Kubernetes HPA API. Add a **circuit breaker** here — refuse to act if too many actions have fired fleet-wide in the last N seconds, and escalate to a human instead.

5. **ML**: Retrain on real Prometheus/cAdvisor data with the same 6-feature vector. The `predict_state()` function signature is the contract; nothing else in the pipeline changes.

---

*Built as a self-contained prototype demonstrating the full Pulse architecture in a single process.*

---

## 🛡 Safety Layer (Anti-Thrashing)

Two independent guards protect the fleet from Pulse itself:

1. **Scoped cooldown (per container, per pipeline)** - after acting on a
   container it is protected for `COOLDOWN_SECONDS = 20`. Keys are scoped as
   `cooldown:{pipeline_id}:{container_id}` (in-memory in the prototype,
   Redis TTL keys via `redis_bridge.py` in production) so one pipeline's
   cooldown can never suppress another pipeline's legitimate remediation.

2. **Fleet-wide circuit breaker** - a sliding window (`6 actions / 60 s`).
   Under a systemic event the breaker trips, autonomous action stops, and
   throttled **ESCALATE** rows appear in the audit trail instead of hundreds
   of restarts. Verified by `tests/stress_test.py` under mass failure.

## 📡 Telemetry Agents (production path)

`agent/` contains both implementations of the telemetry contract described on
PPTX slide 7: a zero-dependency **C++17 agent** reading the Docker unix socket
and a Python reference agent. Both emit one JSON line per container every 3 s
tagged with the container's `pulse.pipeline` label, and optionally PUBLISH to
Redis on `pulse.telemetry`. See `agent/README.md`.

## 🐳 Full Stack with Docker Compose

```bash
docker compose up --build
# dashboard  -> http://localhost:8080
# backend API -> http://localhost:8000/api/health
```

Brings up Redis (fan-in + TTL cooldowns), TimescaleDB (metrics + audit), the
FastAPI control engine, and an nginx-served dashboard that proxies `/api`
and `/ws`. Without those services configured the backend automatically falls
back to SQLite + in-memory stores - the demo never depends on infrastructure.

## ✅ Tests & Hardening

```bash
cd backend
python -m pytest tests -q          # 25 unit tests
python -m tests.stress_test        # 120 pipelines / 360 containers
```

The stress test asserts: tick latency stays within budget (~20 ms avg for 360
containers thanks to batched inference), the circuit breaker trips under mass
failure injection instead of firing 360 restarts, and cooldown scoping holds
across pipelines.
