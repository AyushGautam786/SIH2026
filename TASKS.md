# Pulse — Master Task List & Agent Continuity Document

> **READ THIS FIRST.** This file is the single source of truth for completing the
> Pulse project (`d:\Project\SIH`). If you are a new agent/session picking this up,
> work top-to-bottom through unchecked tasks, keep this file updated (mark `[x]`
> when done), and never leave the project in a non-compiling state between tasks.
>
> - Spec sources: `Pulse (1).pptx` + `Pulse_Project_Explanation.pdf` (Downloads).
> - Prototype already works: FastAPI + React/Vite. Run instructions in `README.md`.
> - Backend deps: `pip install -r d:\Project\SIH\backend\requirements.txt`.
> - Frontend deps: `cd d:\Project\SIH\frontend && npm install`.
> - Verification commands live at the bottom of this file.

## Ground rules for any agent
1. Do tasks in order. Each task ends with the project runnable.
2. Production-grade components (Redis/Postgres/Docker/C++ agent) MUST degrade
   gracefully when real infrastructure is absent — guard imports, fall back to
   prototype implementations. The demo must always run on Windows with no extra
   services installed.
3. Do not add npm dependencies (frontend uses only react/react-dom/vite). Build
   topology graph + charts as custom SVG components.
4. After each phase: update the checkboxes here, then run verification commands.

## Phase 0 — Continuity doc ✅
- [x] 0.1 Create this TASKS.md before touching code.

## Phase 1 — Backend core upgrades (simulator + registry)
- [x] 1.1 Rewrite `backend/simulator.py` → richer telemetry per PPTX slides 12/13:
      cpu %, mem % + mem_mb vs mem_limit_mb, disk_read_bps/disk_write_bps,
      net_rx_bps/net_tx_bps, tcp_connections, packet_drops. Tick target 3 s.
      Keep scenario injection API (healthy/spike/at_risk) + `recover()`.
      Add configurable pipelines/containers constructor args.
- [x] 1.2 New `backend/registry.py` → `PipelineRegistry`: registers pipelines +
      containers, resolves pipeline context, scopes lookups by
      `(pipeline_id, container_id)` (PPTX objective 03 "Pipeline Isolation").
      Wire into fleet creation in `main.py`.

## Phase 2 — ML upgrade
- [x] 2.1 Upgrade `backend/ml_model.py`:
      - Fixed feature order (documented): cpu_latest, mem_latest, net_latest,
        cpu_rolling_avg_20 (~1m @3s), cpu_rolling_avg_100 (~5m over available),
        mem_delta_30s, net_std_60s, cpu_mem_ratio. Use numpy/pandas.
      - Training data shaped like simulator scenarios WITH predictive labeling:
        the ~3-minute window (≈60 ticks) preceding failure labeled at_risk
        ("impending crash") — PPTX slide 13.
      - Persist model to `backend/models/rf_model.joblib` (joblib); load at
        startup if present else train+save. Expose `model_info()`.
      - Keep `predict_state(history)` signature identical (interface contract).

## Phase 3 — Safety layer (anti-thrashing)
- [x] 3.1 Extend `backend/control.py`:
      - Cooldown keyed by composite `(pipeline_id, container_id)` helper.
      - NEW `CircuitBreaker`: sliding-window counter of fleet-wide actions;
        if > MAX_ACTIONS_IN_WINDOW (e.g. 6 / 60 s) refuse action and return
        `"escalate"` so the loop logs an escalation instead of acting.
- [x] 3.2 New `backend/redis_bridge.py` → optional production pieces with
      graceful fallback (guard `import redis`):
      - `RedisCooldownStore(CooldownStore)` using key
        `cooldown:{pipeline_id}:{container_id}` + `SET ... EX 20` (slide 9).
      - `make_cooldown_store()` factory: Redis impl if reachable else InMemory.

## Phase 4 — Storage layer
- [x] 4.1 Extend `backend/store.py`:
      - Keep `SQLiteAuditStore` default. Add `SQLiteMetricsStore` time-series
        writes with pruning; powers `/api/history/{container_id}`.
      - Guarded `PostgresAuditStore`/`TimescaleMetricsStore` stubs using env
        var `PULSE_DB_DSN` (lazy psycopg2 import). Factories `make_audit_store()`,
        `make_metrics_store()` in store.py.
- [x] 4.2 New `backend/executor.py`: `DockerActionExecutor(ActionExecutor)`
      using docker-py (lazy import); `PULSE_EXECUTOR=simulated|docker`

## Phase 5 — API wiring
- [x] 5.1 Update `backend/main.py`: TICK_SECONDS = 3. Wire registry, cooldown
      factory, circuit breaker, metrics store into the detect→predict→heal
      loop. On breaker trip, log an `escalate` row to audit store.
      New endpoints: `GET /api/pipelines` (worst-state rollup),
      `GET /api/history/{container_id}?points=120`, `GET /api/model/info`,
      `GET /api/config`. WS payload gains new metric fields (additive only).
- [x] 5.2 Update `backend/requirements.txt` (pandas, joblib, pytest; commented
      optional extras: redis, docker, psycopg2-binary). Verify clean run:
      `python -m uvicorn main:app --port 8000`.

## Phase 6 — Tests + hardening
- [x] 6.1 `backend/tests/`: `test_ml.py` (feature shape, accuracy >0.95 on
      held-out synthetic split), `test_control.py` (cooldown expiry,
      choose_action dominance, circuit breaker trip/recover), `test_store.py`
      (audit + metrics roundtrip), `test_registry.py`.
- [x] 6.2 `backend/tests/stress_test.py` → 100+ pipelines through loop logic
      (no server): assert tick latency budget and cooldown/breaker hold under
      mass-failure injection. Runnable via `python -m tests.stress_test`.
- [x] 6.3 All tests pass: `cd backend && python -m pytest tests -q`.

## Phase 7 — Telemetry agents (production path artifacts)
- [x] 7.1 `agent/pulse_agent.cpp` — C++17 agent: reads Docker unix socket
      (`/var/run/docker.sock`, GET /containers/{id}/stats?stream=false), adds
      `pipeline_id` from container labels (`pulse.pipeline`), emits one JSON
      line per sample every 3 s (hand-rolled JSON, zero deps). Include
      `agent/README.md` with g++ compile command. Windows compile NOT required.
- [x] 7.2 `agent/pulse_agent.py` — equivalent Python reference agent (docker-py
      or raw socket), publishing to stdout or Redis if `REDIS_URL` set.

## Phase 8 — Deployment artifacts
- [x] 8.1 Root `docker-compose.yml`: services redis, postgres (timescale image),
      backend (env REDIS_URL, PULSE_DB_DSN), frontend (nginx serving dist +
      proxying /ws and /api to backend).
- [x] 8.2 `backend/Dockerfile`, `frontend/Dockerfile`, `frontend/nginx.conf`,
      `.env.example`, root `.dockerignore`.

## Phase 9 — Frontend completion (no new npm deps)
- [x] 9.1 `src/lib/api.js` — central WS/REST client + shared helpers (extract
      from App.jsx; keep seeded-preview fallback when backend offline).
- [x] 9.2 `src/components/MetricChart.jsx` — SVG sparkline/area chart fed by
      client-side rolling history from WS ticks (cpu/mem/net/disk, ~60 pts).
- [x] 9.3 `src/components/TopologyGraph.jsx` — SVG topology: pipeline nodes →
      container nodes, edges colored by worst state, click selects container.
      Static layout acceptable; must match glassmorphism tokens.
- [x] 9.4 `src/components/PipelineGroup.jsx` — fleet grouped by pipeline;
      pipeline status = worst container state (PPTX slide 11).
- [x] 9.5 `src/components/ContainerDetail.jsx` — drawer/modal: big live charts,
      feature readout (cpu avg, mem delta, net std, ratio), confidence,
      cooldown timer, recent actions for that container.
- [x] 9.6 Rework `PrototypePage` in App.jsx into tabbed views
      `Fleet | Topology | Audit`; wire new components + stats bar (pipelines,
      at-risk, actions). Keep existing card grid inside Fleet view.
- [x] 9.7 CSS additions in App.css/index.css using existing token naming.
- [x] 9.8 `npm run build` passes; all tabs render with seeded preview data when
      backend offline (existing behavior must not regress).

## Phase 10 — Docs + final verification
- [x] 10.1 Update `README.md`: architecture diagram (text), new endpoints,
       8-feature vector rationale, safety section (cooldown scoping + circuit
       breaker), agents, docker-compose quickstart, demo script mapped to PPTX
       outcomes (slide 17).
- [x] 10.2 Final run-through of verification commands; mark phases done here.

---

## Verification commands
```powershell
cd d:\Project\SIH\backend
pip install -r requirements.txt
python -m pytest tests -q
python -m uvicorn main:app --port 8000   # GET http://localhost:8000/api/health

cd d:\Project\SIH\frontend
npm install
npm run build
npm run dev                              # http://localhost:5173/#prototype

cd d:\Project\SIH\backend
python -m tests.stress_test
```

## Key design contracts (do not break)
- `interfaces.py` is the contract wall: main.py/ml_model.py never import
  concrete impls except at the single WIRING block in main.py.
- `ml_model.predict_state(history) -> (label, confidence)` signature is frozen.
- WS message shape `{type:"tick", ts, containers:[...]}` — additive changes only.
- Everything production-grade must no-op gracefully without its infra.

      (default simulated). Restart vs scale decision stays in control.py.
