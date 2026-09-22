import pytest

from services.agents.orchestrator import route_after_review
from services.agents.orchestrator.graph import WORKFLOW_NODES, build_graph


def test_review_routes_to_revision_at_most_twice() -> None:
    assert route_after_review({"review_blocking": True, "revision_count": 0, "max_auto_revisions": 2}) == "revise"
    assert route_after_review({"review_blocking": True, "revision_count": 1, "max_auto_revisions": 2}) == "revise"
    assert route_after_review({"review_blocking": True, "revision_count": 2, "max_auto_revisions": 2}) == "insight"
    assert route_after_review({"review_blocking": False, "revision_count": 0}) == "insight"


def test_graph_rejects_publish_node() -> None:
    nodes = {name: lambda _state: {} for name in WORKFLOW_NODES}
    nodes["publish"] = lambda _state: {}
    with pytest.raises(ValueError, match="publish"):
        build_graph(nodes)


def test_graph_executes_finite_revision_path() -> None:
    calls = []

    def node(name):
        def run(state):
            calls.append(name)
            return {"review_blocking": name == "review"}

        return run

    graph = build_graph({name: node(name) for name in WORKFLOW_NODES})
    result = graph.invoke(
        {
            "run_id": "run-1",
            "input_snapshot_id": "snapshot-1",
            "revision_count": 0,
            "max_auto_revisions": 2,
            "node_runs": [],
        }
    )
    assert calls == [
        "brand",
        "strategy",
        "content",
        "review",
        "content",
        "review",
        "content",
        "review",
        "insight",
        "recommendation",
    ]
    assert result["revision_count"] == 2
    assert len(result["node_runs"]) == 10
