import pytest

from datalake_canvas.executor import CycleError, WorkflowError, WorkflowExecutor, topological_order
from datalake_canvas.models import (
    ChartSpec,
    DataSourceRef,
    TableData,
    WorkflowEdge,
    WorkflowIn,
    WorkflowNode,
)
from datalake_canvas.nodes import NodeError, TransformConfig, apply_transform
from tests.conftest import FakeGateway


def node(id_, type_, **data):
    return WorkflowNode(id=id_, type=type_, data=data)


def edge(a, b):
    return WorkflowEdge(source=a, target=b)


# --- topological_order ------------------------------------------------------


def test_topological_order_respects_dependencies():
    nodes = [node("c", "chart"), node("b", "transform"), node("a", "data_source")]
    assert topological_order(nodes, [edge("a", "b"), edge("b", "c")]) == ["a", "b", "c"]


def test_topological_order_is_deterministic_for_independent_nodes():
    nodes = [node("x", "query"), node("y", "query"), node("z", "query")]
    assert topological_order(nodes, []) == ["x", "y", "z"]


def test_topological_order_handles_diamond():
    nodes = [node(i, "query") for i in "abcd"]
    order = topological_order(
        nodes, [edge("a", "b"), edge("a", "c"), edge("b", "d"), edge("c", "d")]
    )
    assert order[0] == "a" and order[-1] == "d"


def test_cycle_detected():
    nodes = [node("a", "query"), node("b", "query")]
    with pytest.raises(CycleError, match="a, b"):
        topological_order(nodes, [edge("a", "b"), edge("b", "a")])


def test_self_loop_is_a_cycle():
    with pytest.raises(CycleError):
        topological_order([node("a", "query")], [edge("a", "a")])


def test_unknown_node_in_edge():
    with pytest.raises(WorkflowError, match="unknown node"):
        topological_order([node("a", "query")], [edge("a", "ghost")])


# --- end-to-end through the executor ---------------------------------------


def pipeline(sql="SELECT 1", **chart):
    return WorkflowIn(
        name="t",
        nodes=[
            node("ds", "data_source", datasource_id="demo"),
            node("q", "query", sql=sql),
            node("t", "transform", operation="sort", column="revenue", descending=True),
            node("c", "chart", **({"chart_type": "bar", "x": "region", "y": "revenue"} | chart)),
        ],
        edges=[edge("ds", "q"), edge("q", "t"), edge("t", "c")],
    )


async def test_full_pipeline(sales_table):
    gateway = FakeGateway({"SELECT 1": sales_table})
    result = await WorkflowExecutor(gateway).run(pipeline(), workflow_id="wf1")

    assert result.status == "success"
    assert result.workflow_id == "wf1"
    assert result.order == ["ds", "q", "t", "c"]
    assert gateway.calls == [("demo", "SELECT 1")]
    assert result.results["ds"].output == DataSourceRef(datasource_id="demo")

    chart = result.results["c"].output
    assert isinstance(chart, ChartSpec)
    # sorted descending by revenue, NULL last
    assert [r[0] for r in chart.data.rows] == ["NA", "EU", "APAC", "LATAM"]


async def test_failure_skips_downstream_but_not_independent_branches(sales_table):
    wf = pipeline(sql="SELECT missing")  # gateway has no canned result -> query node fails
    wf.nodes.append(node("ds2", "data_source", datasource_id="demo"))
    result = await WorkflowExecutor(FakeGateway({"SELECT 1": sales_table})).run(wf)

    assert result.status == "failed"
    assert result.results["q"].status == "error"
    assert "no canned result" in result.results["q"].error
    assert result.results["t"].status == "skipped"
    assert result.results["c"].status == "skipped"
    assert result.results["ds2"].status == "success"  # independent branch still ran


async def test_query_without_datasource_errors():
    wf = WorkflowIn(name="t", nodes=[node("q", "query", sql="SELECT 1")])
    result = await WorkflowExecutor(FakeGateway()).run(wf)
    assert "Data Source" in result.results["q"].error


async def test_query_can_use_datasource_id_from_its_own_config(sales_table):
    wf = WorkflowIn(name="t", nodes=[node("q", "query", sql="S", datasource_id="demo")])
    result = await WorkflowExecutor(FakeGateway({"S": sales_table})).run(wf)
    assert result.status == "success"


async def test_unknown_datasource_reported():
    wf = WorkflowIn(name="t", nodes=[node("ds", "data_source", datasource_id="nope")])
    result = await WorkflowExecutor(FakeGateway()).run(wf)
    assert "Unknown data source" in result.results["ds"].error


async def test_invalid_config_gives_readable_error():
    wf = WorkflowIn(name="t", nodes=[node("ds", "data_source")])
    result = await WorkflowExecutor(FakeGateway()).run(wf)
    assert result.results["ds"].status == "error"
    assert "datasource_id" in result.results["ds"].error


async def test_chart_with_unknown_column(sales_table):
    result = await WorkflowExecutor(FakeGateway({"SELECT 1": sales_table})).run(pipeline(y="nope"))
    assert "Unknown column 'nope'" in result.results["c"].error


async def test_transform_without_table_input():
    wf = WorkflowIn(name="t", nodes=[node("t", "transform", operation="limit", n=1)])
    result = await WorkflowExecutor(FakeGateway()).run(wf)
    assert "needs a Query or Transform" in result.results["t"].error


async def test_cycle_raises_before_running_anything():
    wf = WorkflowIn(
        name="t", nodes=[node("a", "query", sql="x"), node("b", "query", sql="y")],
        edges=[edge("a", "b"), edge("b", "a")],
    )  # fmt: skip
    gateway = FakeGateway()
    with pytest.raises(CycleError):
        await WorkflowExecutor(gateway).run(wf)
    assert gateway.calls == []


def test_workflow_model_rejects_dangling_edges_and_duplicate_ids():
    with pytest.raises(ValueError, match="unknown node"):
        WorkflowIn(name="t", nodes=[node("a", "query")], edges=[edge("a", "b")])
    with pytest.raises(ValueError, match="unique"):
        WorkflowIn(name="t", nodes=[node("a", "query"), node("a", "chart")])


# --- transforms ---------------------------------------------------------------


async def run_transform(table: TableData, **cfg) -> TableData:
    wf = WorkflowIn(
        name="t",
        nodes=[node("q", "query", sql="S", datasource_id="demo"), node("t", "transform", **cfg)],
        edges=[edge("q", "t")],
    )
    result = await WorkflowExecutor(FakeGateway({"S": table})).run(wf)
    out = result.results["t"]
    assert out.status == "success", out.error
    return out.output


async def test_transform_limit_select_filter(sales_table):
    assert (await run_transform(sales_table, operation="limit", n=2)).rows == sales_table.rows[:2]

    selected = await run_transform(sales_table, operation="select", columns="revenue")
    assert selected.columns == ["revenue"] and selected.rows[0] == [120.5]

    big = await run_transform(
        sales_table, operation="filter", column="revenue", op=">", value="100"
    )
    assert [r[0] for r in big.rows] == [
        "EU",
        "NA",
    ]  # numeric compare against a string value; NULL excluded

    contains = await run_transform(
        sales_table, operation="filter", column="region", op="contains", value="a"
    )
    assert {r[0] for r in contains.rows} == {"NA", "APAC", "LATAM"}


@pytest.mark.parametrize(
    ("aggregate_op", "expected"),
    [
        ("sum", [["North", 4.0], ["South", 10.0], [None, 5.0], ["Empty", None]]),
        ("avg", [["North", 2.0], ["South", 10.0], [None, 5.0], ["Empty", None]]),
        ("count", [["North", 2], ["South", 1], [None, 1], ["Empty", 0]]),
        ("min", [["North", 1], ["South", 10], [None, 5], ["Empty", None]]),
        ("max", [["North", 3], ["South", 10], [None, 5], ["Empty", None]]),
    ],
)
async def test_transform_aggregate(aggregate_op, expected):
    table = TableData(
        columns=["region", "revenue"],
        rows=[
            ["North", 1],
            ["South", None],
            ["North", 3],
            [None, 5],
            ["South", 10],
            ["Empty", None],
        ],
    )

    result = await run_transform(
        table,
        operation="aggregate",
        group_by="region",
        aggregate_op=aggregate_op,
        column="revenue",
    )

    assert result.columns == ["region", f"{aggregate_op}_revenue"]
    assert result.rows == expected


async def test_transform_aggregate_errors():
    table = TableData(
        columns=["region", "revenue"], rows=[["North", 1], ["South", object()], ["South", object()]]
    )

    with pytest.raises(Exception, match="requires numeric values"):
        await run_transform(
            table,
            operation="aggregate",
            group_by="region",
            aggregate_op="sum",
            column="revenue",
        )

    with pytest.raises(Exception, match="not comparable"):
        await run_transform(
            table,
            operation="aggregate",
            group_by="region",
            aggregate_op="min",
            column="revenue",
        )


def test_transform_aggregate_reports_the_real_problem_with_the_columns():
    table = TableData(columns=["region", "revenue"], rows=[["EU", 1]])
    config = {"operation": "aggregate", "aggregate_op": "sum", "column": "revenue"}

    with pytest.raises(NodeError, match="aggregate requires 'group_by'"):
        apply_transform(table, TransformConfig(**config))
    # a group_by that is set but names a missing column must say so, not claim it is missing
    with pytest.raises(NodeError, match="Unknown column 'nope'"):
        apply_transform(table, TransformConfig(**config, group_by="nope"))
