"""Pydantic schemas shared by the API, the store and the executor."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, model_validator


class NodeType(StrEnum):
    DATA_SOURCE = "data_source"
    QUERY = "query"
    TRANSFORM = "transform"
    CHART = "chart"


class Position(BaseModel):
    x: float = 0
    y: float = 0


class WorkflowNode(BaseModel):
    id: str = Field(min_length=1)
    type: NodeType
    position: Position = Field(default_factory=Position)
    # Node configuration (e.g. {"sql": "..."}). Validated per node type at run time
    # (see nodes.py) so half-configured nodes can still be saved from the canvas.
    data: dict[str, Any] = Field(default_factory=dict)


class WorkflowEdge(BaseModel):
    id: str | None = None
    source: str
    target: str


class WorkflowIn(BaseModel):
    """A workflow as sent by clients (no server-assigned fields)."""

    name: str = Field(min_length=1, max_length=200)
    nodes: list[WorkflowNode] = Field(default_factory=list)
    edges: list[WorkflowEdge] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_structure(self) -> WorkflowIn:
        ids = [n.id for n in self.nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("node ids must be unique")
        known = set(ids)
        for e in self.edges:
            if e.source not in known or e.target not in known:
                raise ValueError(f"edge {e.source!r} -> {e.target!r} references an unknown node")
        return self


class Workflow(WorkflowIn):
    id: str
    created_at: datetime
    updated_at: datetime


class WorkflowSummary(BaseModel):
    id: str
    name: str
    node_count: int
    updated_at: datetime


# --- node outputs & run results -------------------------------------------


class TableData(BaseModel):
    kind: Literal["table"] = "table"
    columns: list[str]
    rows: list[list[Any]]
    truncated: bool = False


class DataSourceRef(BaseModel):
    kind: Literal["datasource"] = "datasource"
    datasource_id: str


class ChartSpec(BaseModel):
    kind: Literal["chart"] = "chart"
    chart_type: Literal["bar", "line"]
    x: str
    y: str
    data: TableData


NodeOutput = Annotated[TableData | DataSourceRef | ChartSpec, Field(discriminator="kind")]


class NodeResult(BaseModel):
    node_id: str
    status: Literal["success", "error", "skipped"]
    output: NodeOutput | None = None
    error: str | None = None
    duration_ms: float = 0


class RunResult(BaseModel):
    workflow_id: str | None = None
    status: Literal["success", "failed"]
    order: list[str]
    results: dict[str, NodeResult]
