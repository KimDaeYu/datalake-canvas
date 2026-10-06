"""Spawns the real SQLite MCP server over stdio and drives it through the backend wrapper."""

import json
import sys

import pytest

from datalake_canvas.executor import WorkflowExecutor
from datalake_canvas.gateway import MCPDataGateway
from datalake_canvas.mcp_client import MCPClient, MCPServerSpec, MCPToolError
from datalake_canvas.models import ChartSpec, WorkflowIn
from datalake_canvas.registry import ConfigError, DataSourceRegistry
from datalake_canvas.safety import SafetyGuard, SafetyViolation
from tests.conftest import REPO_ROOT


@pytest.fixture
def gateway(demo_db):
    spec = MCPServerSpec(
        id="demo-sqlite",
        name="Demo",
        dialect="sqlite",
        command=sys.executable,
        args=[str(REPO_ROOT / "mcp-servers" / "sqlite" / "server.py")],
        env={"SQLITE_DB_PATH": str(demo_db)},
    )
    return MCPDataGateway(
        DataSourceRegistry([spec]), MCPClient(timeout=30), SafetyGuard(), max_rows=1000
    )


async def test_list_and_describe(gateway):
    assert await gateway.list_tables("demo-sqlite") == ["customers", "orders", "products"]
    info = await gateway.describe_table("demo-sqlite", "products")
    assert [c["name"] for c in info["columns"]] == ["id", "name", "category", "price"]


async def test_run_select_and_truncation(gateway):
    table = await gateway.run_select("demo-sqlite", "SELECT COUNT(*) AS n FROM orders")
    assert table.columns == ["n"] and table.rows == [[600]]

    limited = await gateway.run_select("demo-sqlite", "SELECT id FROM orders", max_rows=5)
    assert len(limited.rows) == 5 and limited.truncated


async def test_guard_blocks_before_reaching_server(gateway):
    with pytest.raises(SafetyViolation):
        await gateway.run_select("demo-sqlite", "DELETE FROM orders")


async def test_server_rejects_writes_even_if_guard_is_bypassed(demo_db):
    """Defense in depth: the MCP server itself refuses writes."""
    spec = MCPServerSpec(
        id="d", name="d", command=sys.executable,
        args=[str(REPO_ROOT / "mcp-servers" / "sqlite" / "server.py")],
        env={"SQLITE_DB_PATH": str(demo_db)},
    )  # fmt: skip
    with pytest.raises(MCPToolError, match="Only SELECT"):
        await MCPClient().call_tool(spec, "run_select", {"sql": "DELETE FROM orders"})
    # ...and a write smuggled behind a SELECT prefix hits the read-only connection.
    with pytest.raises(MCPToolError):
        await MCPClient().call_tool(
            spec, "run_select", {"sql": "WITH x AS (SELECT 1) DELETE FROM orders"}
        )


async def test_server_errors_surface_as_mcp_tool_error(gateway):
    with pytest.raises(MCPToolError, match="no such table"):
        await gateway.run_select("demo-sqlite", "SELECT * FROM missing_table")


async def test_example_workflow_runs_against_real_server(gateway):
    example = json.loads(
        (REPO_ROOT / "examples" / "workflows" / "revenue-by-category.json").read_text()
    )
    result = await WorkflowExecutor(gateway).run(WorkflowIn.model_validate(example))
    assert result.status == "success", {k: v.error for k, v in result.results.items()}
    chart = result.results["c"].output
    assert isinstance(chart, ChartSpec)
    revenues = [r[1] for r in chart.data.rows]
    assert revenues == sorted(revenues, reverse=True) and len(revenues) == 4


def test_registry_expands_variables_and_fails_loudly(tmp_path, monkeypatch):
    cfg = tmp_path / "ds.json"
    cfg.write_text(
        json.dumps(
            {
                "datasources": [
                    {
                        "id": "a", "name": "A", "command": "python",
                        "args": ["${ROOT}/server.py"], "env": {"DSN": "${MY_SECRET_DSN}"},
                    }
                ]
            }
        )
    )  # fmt: skip
    monkeypatch.setenv("MY_SECRET_DSN", "postgresql://u:p@h/db")
    spec = DataSourceRegistry.from_file(cfg, {"ROOT": "/srv"}).get("a")
    assert spec.command == sys.executable
    assert spec.args == ["/srv/server.py"] and spec.env == {"DSN": "postgresql://u:p@h/db"}

    monkeypatch.delenv("MY_SECRET_DSN")
    with pytest.raises(ConfigError, match="MY_SECRET_DSN"):
        DataSourceRegistry.from_file(cfg, {"ROOT": "/srv"})
