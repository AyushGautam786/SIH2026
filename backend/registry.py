"""
registry.py — Pipeline Registry (PPTX objective 03: "Pipeline Isolation").

Every container in Pulse belongs to exactly one pipeline. The registry is the
authoritative map of pipeline -> containers and provides:

  - scoped lookups: state and actions are always resolved through a
    (pipeline_id, container_id) pair, never a bare container id;
  - fleet rollups: a pipeline's status equals its WORST container state,
    which is what the dashboard's fleet-overview grid renders.

The control engine consults the registry before issuing remediation so one
pipeline's cooldown or failure can never leak into another's.
"""
from collections import OrderedDict

# Canonical severity ordering used for worst-state rollups everywhere.
STATE_SEVERITY = {"at_risk": 0, "transient_spike": 1, "healthy": 2}


def composite_key(pipeline_id: str | None, container_id: str) -> tuple[str, str]:
    """Scoped key helper shared with the cooldown store (PPTX slide 9:
    cooldown:{pipeline_id}:{container_id}). A missing pipeline degrades to a
    wildcard scope rather than crashing — prototype data may lack the tag."""
    return (pipeline_id or "*", container_id)


class PipelineRegistry:
    def __init__(self) -> None:
        self._pipelines: OrderedDict[str, list[str]] = OrderedDict()
        self._container_pipeline: dict[str, str] = {}

    # ---- registration ----------------------------------------------------
    def register_container(self, container_id: str, pipeline_id: str) -> None:
        if pipeline_id not in self._pipelines:
            self._pipelines[pipeline_id] = []
        if container_id not in self._pipelines[pipeline_id]:
            self._pipelines[pipeline_id].append(container_id)
        self._container_pipeline[container_id] = pipeline_id

    # ---- lookups ----------------------------------------------------------
    def pipeline_of(self, container_id: str) -> str | None:
        return self._container_pipeline.get(container_id)

    def containers_of(self, pipeline_id: str) -> list[str]:
        return list(self._pipelines.get(pipeline_id, []))

    def pipelines(self) -> list[str]:
        return list(self._pipelines.keys())

    def resolve_scope(self, container_id: str) -> tuple[str, str]:
        """Full scoped identity for cooldown keys / audit rows."""
        return composite_key(self.pipeline_of(container_id), container_id)

    # ---- rollups ------------------------------------------------------------
    def worst_state(self, pipeline_id: str, states_by_container: dict[str, str]) -> str:
        """Pipeline health = its worst container's predicted state."""
        severities = [
            STATE_SEVERITY.get(states_by_container.get(cid, "healthy"), 2)
            for cid in self.containers_of(pipeline_id)
        ]
        if not severities:
            return "healthy"
        worst = min(severities)
        return {v: k for k, v in STATE_SEVERITY.items()}[worst]

    def overview(self, states_by_container: dict[str, str]) -> list[dict]:
        """Shape consumed by GET /api/pipelines and the dashboard grid."""
        out = []
        for pid in self.pipelines():
            cids = self.containers_of(pid)
            out.append({
                "pipeline": pid,
                "containers": len(cids),
                "status": self.worst_state(pid, states_by_container),
                "container_ids": cids,
            })
        return out
