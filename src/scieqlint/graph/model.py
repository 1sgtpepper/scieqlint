"""Graph export model."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal

GraphNodeKind = Literal["equation", "reference"]
GraphEdgeKind = Literal["references"]


@dataclass(frozen=True, slots=True)
class GraphSpan:
    path: PurePosixPath
    line: int
    col: int
    end_line: int
    end_col: int
    cell: int | None = None
    cell_line: int | None = None


@dataclass(frozen=True, slots=True)
class GraphNode:
    id: str
    kind: GraphNodeKind
    label: str | None
    source: str
    span: GraphSpan


@dataclass(frozen=True, slots=True)
class GraphEdge:
    source: str
    target: str
    kind: GraphEdgeKind
    target_label: str
    raw: str
    source_kind: str


@dataclass(frozen=True, slots=True)
class Graph:
    schema_version: str
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]
