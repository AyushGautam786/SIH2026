"""
main.py — Pulse backend (detect → predict → heal engine).

Run with:  python -m uvicorn main:app --port 8000

Dashboard connects to: ws://localhost:8000/ws

--------------------------------------------------------------------------
UPGRADE POINT: everything in the "wiring" section constructs concrete
implementations of the four interfaces in interfaces.py (plus the pipeline
registry, circuit breaker and metrics store). To move any piece of Pulse to
production, implement the interface and change ONLY the constructor call
here. The loop logic below never changes, because it only ever calls
interface methods.
--------------------------------------------------------------------------
"""
import asyncio
import json
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

import control
import executor as executor_factory_module
import ml_model
import store
from redis_bridge import make_cooldown_store
from registry import PipelineRegistry
from simulator import TICK_SECONDS, SimulatedFleet

# ---- WIRING: swap any of these for their production counterpart ----------
fleet    = SimulatedFleet(n_containers=6)          # -> DockerTelemetrySource
registry = PipelineRegistry()
for cid, c in fleet.containers.items():
    registry.register_container(cid, c.pipeline)

guard    = make_cooldown_store()                   # Redis w/ TTL if reachable,
                                                   # else InMemoryCooldownStore
audit    = store.make_audit_store()                # Postgres when PULSE_DB_DSN,
metrics  = store.make_metrics_store()              # TimescaleDB or SQLite
breaker  = control.CircuitBreaker()
throttle = control.EscalationThrottle()
executor = executor_factory_module.make_executor(fleet)   # simulated|docker
# ---------------------------------------------------------------------------

connected_clients: list[WebSocket] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start the detect-predict-heal loop when the server starts."""
    task = asyncio.create_task(detect_predict_heal_loop())
    yield
    task.cancel()


app = FastAPI(title="Pulse — Predictive Self-Healing Engine", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Core loop
# ---------------------------------------------------------------------------

async def detect_predict_heal_loop() -> None:
    """The heart of Pulse: DETECT (tick metrics) -> PREDICT (ML) -> HEAL (act).

    Written entirely against interfaces.py contracts — has no idea whether
    it's talking to a simulator or real Docker. Safety is layered:

      1. per-container cooldown scoped by (pipeline_id, container_id)
         so a restart blip can't re-trigger itself;
      2. fleet-wide circuit breaker (anti-thrashing) — when tripped the
         action is suppressed and an ESCALATION is logged for humans.
    """
    while True:
        fleet.tick()  # DETECT

        containers = list(fleet.containers.values())
        predictions = ml_model.predict_batch(
            [list(c.history) for c in containers]          # PREDICT (batched)
        )

        events = []
        escalations = []
        for c, (state, confidence) in zip(containers, predictions):

            action = None
            escalated = False

            at_risk = state == "at_risk"
            cooling = guard.is_cooling_down(c.id, c.pipeline)

            if at_risk and not cooling:
                if breaker.allow():                       # HEAL (safety-gated)
                    action = control.choose_action(c.snapshot())
                    did_act = executor.execute(c.id, action)
                    if did_act:
                        guard.start_cooldown(c.id, c.pipeline)
                        breaker.record_action()
                        c.last_action = action
                        c.last_action_at = time.time()
                        audit.log_action(
                            c.id, c.name, c.pipeline, state, confidence, action
                        )
                else:
                    # Anti-thrashing tripped: surface to humans instead
                    # (throttled so the audit trail stays readable).
                    escalated = throttle.should_log(c.id)
                    if escalated:
                        breaker.record_escalation()
                        audit.log_escalation(
                            c.id, c.name, c.pipeline, state, confidence
                        )
                        escalations.append({
                            "container_id": c.id,
                            "container_name": c.name,
                            "pipeline": c.pipeline,
                            "predicted_state": state,
                        })

            events.append(
                {
                    **c.snapshot(),
                    "predicted_state": state,
                    "confidence": round(confidence, 2),
                    "cooldown_seconds_left": round(guard.seconds_left(c.id, c.pipeline), 1),
                    "action_taken": action,
                    "escalated": escalated,
                }
            )

        metrics.write_tick(events)   # persist time-series snapshot

        message = {"type": "tick", "containers": events, "ts": time.time()}
        if escalations:
            message["escalations"] = escalations
        await _broadcast(message)
        await asyncio.sleep(TICK_SECONDS)


async def _broadcast(message: dict) -> None:
    dead: list[WebSocket] = []
    for ws in connected_clients:
        try:
            await ws.send_text(json.dumps(message))
        except Exception:
            dead.append(ws)
    for ws in dead:
        connected_clients.remove(ws)


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    connected_clients.append(websocket)
    try:
        while True:
            # Keep alive — client doesn't send meaningful data
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in connected_clients:
            connected_clients.remove(websocket)


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health():
    """Liveness check."""
    return {"status": "ok", "containers": len(fleet.containers)}


@app.get("/api/containers")
def get_containers():
    """Current snapshot of all containers in the fleet."""
    return fleet.snapshot()


@app.get("/api/audit")
def get_audit(limit: int = 50):
    """Recent autonomous actions (most recent first)."""
    return audit.recent_actions(limit)


@app.get("/api/stats")
def get_stats():
    """Aggregated fleet statistics for the dashboard summary bar."""
    containers = fleet.snapshot()
    at_risk_count = sum(1 for c in fleet.containers.values()
                        if guard.is_cooling_down(c.id, c.pipeline))
    return {
        "total_containers": len(containers),
        "total_pipelines": len(registry.pipelines()),
        "at_risk_now": at_risk_count,
        "total_actions": audit.total_actions(),
        "tick_interval_seconds": TICK_SECONDS,
        "breaker": breaker.state(),
    }


@app.get("/api/pipelines")
def get_pipelines():
    """Pipeline rollup — each pipeline's status equals its worst container
    (PPTX slide 11 'Fleet overview grid')."""
    states = {cid: "healthy" for cid in fleet.containers}
    # Use the freshest predicted states from the last tick if available.
    for c in fleet.containers.values():
        state, _ = ml_model.predict_state(list(c.history))
        states[c.id] = state
    return registry.overview(states)


@app.get("/api/history/{container_id}")
def get_history(container_id: str, points: int = 120):
    """Time-series metrics for one container (metrics store backed)."""
    return metrics.history(container_id, points=points)


@app.get("/api/model/info")
def get_model_info():
    """Random Forest introspection: features, importances, artifact path."""
    return ml_model.model_info()


@app.get("/api/config")
def get_config():
    """Runtime configuration + safety-layer status."""
    return {
        "tick_interval_seconds": TICK_SECONDS,
        "cooldown_seconds": control.COOLDOWN_SECONDS,
        "breaker": breaker.state(),
        "executor": type(executor).__name__,
        "cooldown_store": type(guard).__name__,
        "audit_store": type(audit).__name__,
        "metrics_store": type(metrics).__name__,
    }


@app.post("/api/inject/{container_id}/{scenario}")
def inject(container_id: str, scenario: str):
    """Demo control: manually trigger a spike/at_risk episode on a container.
    Prototype-only — there is no equivalent in production."""
    ok = fleet.inject_scenario(container_id, scenario)
    return {"ok": ok}
