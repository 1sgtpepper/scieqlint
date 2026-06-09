"""Graph JSON serialization."""

from __future__ import annotations

import json
from typing import Any

from scieqlint.graph.model import Graph, GraphEdge, GraphNode, GraphSpan


def render_graph_json(graph: Graph) -> str:
    """Render graph data as deterministic JSON."""
    return json.dumps(_graph_payload(graph), indent=2, sort_keys=False) + "\n"


def _graph_payload(graph: Graph) -> dict[str, Any]:
    return {
        "schema_version": graph.schema_version,
        "nodes": [_node_payload(node) for node in graph.nodes],
        "edges": [_edge_payload(edge) for edge in graph.edges],
    }


def _node_payload(node: GraphNode) -> dict[str, Any]:
    return {
        "id": node.id,
        "kind": node.kind,
        "label": node.label,
        "source": node.source,
        "span": _span_payload(node.span),
    }


def _edge_payload(edge: GraphEdge) -> dict[str, Any]:
    return {
        "source": edge.source,
        "target": edge.target,
        "kind": edge.kind,
        "target_label": edge.target_label,
        "raw": edge.raw,
        "source_kind": edge.source_kind,
    }


def _span_payload(span: GraphSpan) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "path": span.path.as_posix(),
        "line": span.line,
        "col": span.col,
        "end_line": span.end_line,
        "end_col": span.end_col,
    }
    if span.cell is not None:
        payload["cell"] = span.cell
    if span.cell_line is not None:
        payload["cell_line"] = span.cell_line
    return payload
