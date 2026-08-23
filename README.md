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
├── README.md
│
├── backend/                       # Python / FastAPI
│   ├── requirements.txt
│   ├── main.py                    # FastAPI app + detect-predict-heal loop
│   ├── interfaces.py              # Abstract contracts for 4 swap-points
│   ├── simulator.py               # SimulatedFleet (TelemetrySource impl)
│   ├── ml_model.py                # Random Forest, feature extraction
│   ├── control.py                 # CooldownStore + ActionExecutor
│   └── store.py                   # SQLiteAuditStore
│
└── frontend/                      # React + Vite
    ├── package.json
    ├── vite.config.js
    ├── index.html
    └── src/
        ├── main.jsx
        ├── App.jsx                # Root: WebSocket + state management
        ├── App.css                # Component styles (glassmorphism theme)
        ├── index.css              # Design tokens + global styles
        └── components/
            ├── Header.jsx         # Brand + stat chips + connection badge
            ├── ContainerCard.jsx  # Per-container card with metric bars
            └── AuditLog.jsx       # Scrolling autonomous action log
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

The classifier is a `RandomForestClassifier` (150 trees, depth 8) trained on **synthetic data shaped to match the three simulator scenarios**. It learns to distinguish:

| Class | CPU | Mem | Net | Rolling Avg CPU | Mem Delta |
|---|---|---|---|---|---|
| `healthy` | ~20% | ~30% | ~50% | similar to current | stable |
| `transient_spike` | ~78% | ~35% | ~85% | **moderate** (key!) | stable |
| `at_risk` | ~85% | ~78% | ~65% | **high** (sustained) | **growing** |

The critical insight is **rolling average CPU** + **memory delta** — a spike has high *current* CPU but a still-moderate *average*, while `at_risk` has both high and sustained. This is what prevents the system from overreacting to short bursts.

**Feature vector** (6 features per prediction):
```
[cpu_latest, mem_latest, net_latest, cpu_rolling_avg, mem_delta, net_std]
```

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
| `GET` | `/api/stats` | Aggregated fleet stats (at-risk count, total actions) |
| `POST` | `/api/inject/{container_id}/{spike\|at_risk}` | Demo: inject a scenario |
| `WS` | `/ws` | Live tick stream pushed every 2 seconds |

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

1. **Observe the fleet** — six simulated containers across three pipelines, streaming live CPU/mem/net every 2 seconds.

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
