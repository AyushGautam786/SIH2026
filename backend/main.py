"""
main.py — Pulse prototype backend.

Run with:  uvicorn main:app --reload --port 8000

Dashboard connects to: ws://localhost:8000/ws

--------------------------------------------------------------------------
UPGRADE POINT: everything below in the "wiring" section constructs concrete
implementations of the four interfaces in interfaces.py. To move any piece
of Pulse to production, write a new class implementing the relevant interface
and change ONLY the constructor call here. The loop logic below never
changes, because it only ever calls interface methods.
--------------------------------------------------------------------------
"""
import asyncio
import json
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

import control
import ml_model
from simulator import SimulatedFleet
from store import SQLiteAuditStore

# ---- WIRING: swap any of these four for their production counterpart ----
fleet    = SimulatedFleet(n_containers=6)          # -> DockerTelemetrySource
guard    = control.InMemoryCooldownStore()          # -> RedisCooldownStore
audit    = SQLiteAuditStore()                       # -> PostgresAuditStore
executor = control.SimulatedActionExecutor(fleet)   # -> DockerActionExecutor
# -------------------------------------------------------------------------

connected_clients: list[WebSocket] = []
TICK_SECONDS = 2


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
    it's talking to a simulator or real Docker.
    """
    while True:
        fleet.tick()  # DETECT

        events = []
        for c in fleet.containers.values():
            state, confidence = ml_model.predict_state(list(c.history))  # PREDICT
            action = None

            if state == "at_risk" and not guard.is_cooling_down(c.id):
                action = control.choose_action(c.snapshot())
                did_act = executor.execute(c.id, action)  # HEAL
                if did_act:
                    guard.start_cooldown(c.id)
                    c.last_action = action
                    c.last_action_at = time.time()
                    audit.log_action(
                        c.id, c.name, c.pipeline, state, confidence, action
                    )

            events.append(
                {
                    **c.snapshot(),
                    "predicted_state": state,
                    "confidence": round(confidence, 2),
                    "cooldown_seconds_left": round(guard.seconds_left(c.id), 1),
                    "action_taken": action,
                }
            )

        await _broadcast({"type": "tick", "containers": events, "ts": time.time()})
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
                        if guard.is_cooling_down(c.id))
    return {
        "total_containers": len(containers),
        "at_risk_now": at_risk_count,
        "total_actions": audit.total_actions(),
        "tick_interval_seconds": TICK_SECONDS,
    }


@app.post("/api/inject/{container_id}/{scenario}")
def inject(container_id: str, scenario: str):
    """Demo control: manually trigger a spike/at_risk episode on a container.
    Prototype-only — there is no equivalent in production."""
    ok = fleet.inject_scenario(container_id, scenario)
    return {"ok": ok}
