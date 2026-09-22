"""LangGraph workflow wiring with explicit transitions and bounded revisions."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any, Literal, TypedDict


class WorkflowState(TypedDict, total=False):
    run_id: str
    input_snapshot_id: str
    stage: str
    revision_count: int
    max_auto_revisions: int
    review_blocking: bool
    node_runs: list[dict[str, Any]]


Node = Callable[[WorkflowState], Mapping[str, Any]]
WORKFLOW_NODES = ("brand", "strategy", "content", "review", "insight", "recommendation")


def route_after_review(state: WorkflowState) -> Literal["revise", "insight"]:
    """At most two automatic content revisions; then continue with evidence."""

    if state.get("review_blocking", False) and state.get("revision_count", 0) < state.get("max_auto_revisions", 2):
        return "revise"
    return "insight"


def _tracked_node(name: str, node: Node) -> Node:
    def run(state: WorkflowState) -> Mapping[str, Any]:
        started = datetime.now(timezone.utc)
        result = dict(node(state))
        ended = datetime.now(timezone.utc)
        runs = list(state.get("node_runs", []))
        runs.append(
            {
                "node": name,
                "status": "succeeded",
                "started_at": started.isoformat(),
                "finished_at": ended.isoformat(),
                "input_snapshot_id": state.get("input_snapshot_id"),
            }
        )
        result["stage"] = name
        result["node_runs"] = runs
        if name == "content" and state.get("review_blocking", False):
            result["revision_count"] = state.get("revision_count", 0) + 1
        return result

    return run


def build_graph(nodes: Mapping[str, Node], *, checkpointer: Any = None):
    """Build and compile the finite graph using LangGraph.

    The import is lazy so deterministic contract/RAG/analytics tests do not
    require a graph runtime.  Production worker images install the declared
    LangGraph dependency and provide checkpointing at the job boundary.
    """

    missing = [name for name in WORKFLOW_NODES if name not in nodes]
    if missing:
        raise ValueError(f"missing workflow nodes: {missing}")
    if any(name.lower() == "publish" for name in nodes):
        raise ValueError("AI workflow cannot contain a publish node")
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError as error:  # pragma: no cover - exercised in worker image
        raise RuntimeError("LangGraph is required to build the production workflow") from error

    graph = StateGraph(WorkflowState)
    for name in WORKFLOW_NODES:
        graph.add_node(name, _tracked_node(name, nodes[name]))
    graph.add_edge(START, "brand")
    graph.add_edge("brand", "strategy")
    graph.add_edge("strategy", "content")
    graph.add_edge("content", "review")
    graph.add_conditional_edges("review", route_after_review, {"revise": "content", "insight": "insight"})
    graph.add_edge("insight", "recommendation")
    graph.add_edge("recommendation", END)
    return graph.compile(checkpointer=checkpointer)
