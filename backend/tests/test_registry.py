"""Registry tests: pipeline scoping and worst-state rollups."""
from registry import STATE_SEVERITY, PipelineRegistry, composite_key


def _registry():
    reg = PipelineRegistry()
    reg.register_container("c1", "checkout-service")
    reg.register_container("c2", "checkout-service")
    reg.register_container("c3", "auth-service")
    return reg


def test_pipeline_of_and_containers_of():
    reg = _registry()
    assert reg.pipeline_of("c1") == "checkout-service"
    assert sorted(reg.containers_of("checkout-service")) == ["c1", "c2"]
    assert reg.pipelines() == ["checkout-service", "auth-service"]


def test_composite_key_scoping():
    assert composite_key("checkout-service", "c1") == ("checkout-service", "c1")
    # Missing pipeline degrades to a wildcard scope instead of crashing.
    assert composite_key(None, "c1") == ("*", "c1")


def test_resolve_scope_uses_registered_pipeline():
    reg = _registry()
    assert reg.resolve_scope("c3") == ("auth-service", "c3")


def test_worst_state_rollup():
    reg = _registry()
    states = {"c1": "healthy", "c2": "transient_spike"}
    assert reg.worst_state("checkout-service", states) == "transient_spike"
    states["c2"] = "at_risk"
    assert reg.worst_state("checkout-service", states) == "at_risk"
    # Unknown containers default to healthy.
    assert reg.worst_state("auth-service", {}) == "healthy"


def test_severity_ordering_is_canonical():
    assert STATE_SEVERITY["at_risk"] < STATE_SEVERITY["transient_spike"]
    assert STATE_SEVERITY["transient_spike"] < STATE_SEVERITY["healthy"]


def test_overview_shape():
    reg = _registry()
    overview = reg.overview({"c1": "healthy", "c2": "at_risk", "c3": "healthy"})
    by_pid = {row["pipeline"]: row for row in overview}
    assert by_pid["checkout-service"]["status"] == "at_risk"
    assert by_pid["checkout-service"]["containers"] == 2
    assert by_pid["auth-service"]["status"] == "healthy"
