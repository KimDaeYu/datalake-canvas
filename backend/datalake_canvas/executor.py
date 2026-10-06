"""Topological workflow executor.

Nodes run in dependency order. A node receives the outputs of its upstream nodes (in edge
order). If a node fails, everything downstream of it is marked ``skipped`` while
independent branches still run.
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from time import perf_counter

from .gateway import DataGateway
from .models import (
    DataSourceRef,
    NodeOutput,
    NodeResult,
    NodeType,
    RunResult,
    TableData,
    WorkflowEdge,
    WorkflowIn,
    WorkflowNode,
)
from .nodes import (
    ChartConfig,
    DataSourceConfig,
    NodeError,
    QueryConfig,
    TransformConfig,
    apply_transform,
    build_chart,
    parse_config,
)

logger = logging.getLogger(__name__)


class WorkflowError(Exception):
    """The graph itself is invalid (unknown node in an edge, cycle, ...)."""


class CycleError(WorkflowError):
    pass


def topological_order(nodes: list[WorkflowNode], edges: list[WorkflowEdge]) -> list[str]:
    """Kahn's algorithm. Ties keep the order nodes were declared in, so runs are deterministic."""
    ids = [n.id for n in nodes]
    known = set(ids)
    indegree = dict.fromkeys(ids, 0)
    downstream: dict[str, list[str]] = {i: [] for i in ids}
    for e in edges:
        if e.source not in known or e.target not in known:
            raise WorkflowError(f"Edge {e.source!r} -> {e.target!r} references an unknown node")
        downstream[e.source].append(e.target)
        indegree[e.target] += 1

    queue = deque(i for i in ids if indegree[i] == 0)
    order: list[str] = []
    while queue:
        current = queue.popleft()
        order.append(current)
        for nxt in downstream[current]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)

    if len(order) != len(ids):
        stuck = sorted(set(ids) - set(order))
        raise CycleError(f"Workflow contains a cycle involving: {', '.join(stuck)}")
    return order


class WorkflowExecutor:
    def __init__(self, gateway: DataGateway, max_rows: int = 1000) -> None:
        self.gateway = gateway
        self.max_rows = max_rows

    async def run(self, workflow: WorkflowIn, workflow_id: str | None = None) -> RunResult:
        order = topological_order(workflow.nodes, workflow.edges)
        nodes = {n.id: n for n in workflow.nodes}
        upstream: dict[str, list[str]] = defaultdict(list)
        for e in workflow.edges:
            upstream[e.target].append(e.source)

        results: dict[str, NodeResult] = {}
        for node_id in order:
            inputs = [results[src] for src in upstream[node_id]]
            blocked = next((r for r in inputs if r.status != "success"), None)
            if blocked is not None:
                results[node_id] = NodeResult(
                    node_id=node_id,
                    status="skipped",
                    error=f"Skipped because upstream node {blocked.node_id!r} did not succeed",
                )
                continue

            started = perf_counter()
            try:
                output = await self._run_node(
                    nodes[node_id], [r.output for r in inputs if r.output]
                )
                result = NodeResult(node_id=node_id, status="success", output=output)
            except Exception as exc:  # error boundary: one bad node must not abort the run
                if not isinstance(exc, NodeError | WorkflowError):
                    logger.warning("node %s failed: %s", node_id, exc, exc_info=True)
                result = NodeResult(node_id=node_id, status="error", error=str(exc) or repr(exc))
            result.duration_ms = round((perf_counter() - started) * 1000, 2)
            results[node_id] = result

        failed = any(r.status == "error" for r in results.values())
        return RunResult(
            workflow_id=workflow_id,
            status="failed" if failed else "success",
            order=order,
            results=results,
        )

    async def _run_node(self, node: WorkflowNode, inputs: list[NodeOutput]) -> NodeOutput:
        match node.type:
            case NodeType.DATA_SOURCE:
                cfg = parse_config(DataSourceConfig, node.data)
                if not self.gateway.has_datasource(cfg.datasource_id):
                    raise NodeError(f"Unknown data source {cfg.datasource_id!r}")
                return DataSourceRef(datasource_id=cfg.datasource_id)

            case NodeType.QUERY:
                cfg = parse_config(QueryConfig, node.data)
                ref = next((i for i in inputs if isinstance(i, DataSourceRef)), None)
                datasource_id = ref.datasource_id if ref else cfg.datasource_id
                if not datasource_id:
                    raise NodeError("Connect a Data Source node to this query")
                return await self.gateway.run_select(datasource_id, cfg.sql, self.max_rows)

            case NodeType.TRANSFORM:
                cfg = parse_config(TransformConfig, node.data)
                return apply_transform(self._require_table(inputs, "Transform"), cfg)

            case NodeType.CHART:
                cfg = parse_config(ChartConfig, node.data)
                return build_chart(self._require_table(inputs, "Chart"), cfg)

        raise NodeError(f"Unsupported node type {node.type!r}")  # pragma: no cover

    @staticmethod
    def _require_table(inputs: list[NodeOutput], what: str) -> TableData:
        table = next((i for i in inputs if isinstance(i, TableData)), None)
        if table is None:
            raise NodeError(f"{what} node needs a Query or Transform node connected as input")
        return table
