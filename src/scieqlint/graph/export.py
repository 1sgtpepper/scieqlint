"""Build graph data from scanner label and reference outputs."""

from __future__ import annotations

from collections import defaultdict

from scieqlint.diag.model import SourceSpan
from scieqlint.graph.model import Graph, GraphEdge, GraphNode, GraphSpan
from scieqlint.scan.base import EquationLabel, EquationReference

GRAPH_SCHEMA_VERSION = "0.3"


def build_graph(
    labels: tuple[EquationLabel, ...],
    references: tuple[EquationReference, ...],
) -> Graph:
    """Build a stable graph model from scanner outputs."""
    equation_nodes = [_equation_node(label) for label in labels]
    reference_nodes = [_reference_node(reference) for reference in references]
    labels_by_name: dict[str, list[EquationLabel]] = defaultdict(list)
    for label in labels:
        labels_by_name[label.label].append(label)
    edges = [
        (_reference_key(reference), _reference_edge(reference, labels_by_name))
        for reference in references
    ]
    return Graph(
        schema_version=GRAPH_SCHEMA_VERSION,
        nodes=tuple(sorted((*equation_nodes, *reference_nodes), key=_node_key)),
        edges=tuple(edge for _key, edge in sorted(edges, key=lambda item: item[0])),
    )


def _equation_node(label: EquationLabel) -> GraphNode:
    return GraphNode(
        id=_equation_id(label),
        kind="equation",
        label=label.label,
        source=label.source.value,
        span=_span(label.span),
    )


def _reference_node(reference: EquationReference) -> GraphNode:
    return GraphNode(
        id=_reference_id(reference),
        kind="reference",
        label=reference.target,
        source=reference.source.value,
        span=_span(reference.span),
    )


def _reference_edge(
    reference: EquationReference,
    labels_by_name: dict[str, list[EquationLabel]],
) -> GraphEdge:
    return GraphEdge(
        source=_reference_id(reference),
        target=_reference_target(reference, labels_by_name),
        kind="references",
        target_label=reference.target,
        raw=reference.raw,
        source_kind=reference.source.value,
    )


def _span(span: SourceSpan) -> GraphSpan:
    return GraphSpan(
        path=span.path,
        line=span.line,
        col=span.col,
        end_line=span.end_line,
        end_col=span.end_col,
        cell=span.cell,
        cell_line=span.cell_line,
    )


def _equation_id(label: EquationLabel) -> str:
    span = label.span
    cell = "" if span.cell is None else f":cell{span.cell}"
    return f"eq:{span.path.as_posix()}:{span.start}{cell}"


def _label_target_id(label: str) -> str:
    return f"label:{label}"


def _reference_target(
    reference: EquationReference,
    labels_by_name: dict[str, list[EquationLabel]],
) -> str:
    matches = labels_by_name.get(reference.target, [])
    if len(matches) == 1:
        return _equation_id(matches[0])
    return _label_target_id(reference.target)


def _reference_id(reference: EquationReference) -> str:
    span = reference.span
    cell = "" if span.cell is None else f":cell{span.cell}"
    return f"ref:{span.path.as_posix()}:{span.start}{cell}"


def _node_key(node: GraphNode) -> tuple[str, int, int, int, str, str]:
    cell = -1 if node.span.cell is None else node.span.cell
    return (node.span.path.as_posix(), cell, node.span.line, node.span.col, node.kind, node.id)


def _reference_key(reference: EquationReference) -> tuple[str, int, int, int, int, str, str]:
    span = reference.span
    cell = -1 if span.cell is None else span.cell
    return (
        span.path.as_posix(),
        cell,
        span.line,
        span.col,
        span.start,
        reference.target,
        reference.raw,
    )
