"""The seam between the executor/agent and the databases.

The executor only knows :class:`DataGateway`; :class:`MCPDataGateway` is the real
implementation (registry + MCP client + safety guard). Tests substitute a fake.
"""

from __future__ import annotations

from typing import Any, Protocol

from .mcp_client import MCPClient, MCPToolError
from .models import TableData
from .registry import DataSourceRegistry
from .safety import SafetyGuard


class DataGateway(Protocol):
    def has_datasource(self, datasource_id: str) -> bool: ...

    async def run_select(
        self, datasource_id: str, sql: str, max_rows: int | None = None
    ) -> TableData: ...

    async def list_tables(self, datasource_id: str) -> list[str]: ...

    async def describe_table(self, datasource_id: str, table: str) -> dict[str, Any]: ...


class MCPDataGateway:
    """Resolves a data source id to an MCP server and calls its standard tools.

    Servers must expose ``list_tables``, ``describe_table`` and ``run_select``
    (see docs/data-sources.md for the contract).
    """

    def __init__(
        self,
        registry: DataSourceRegistry,
        client: MCPClient,
        guard: SafetyGuard,
        max_rows: int = 1000,
    ) -> None:
        self.registry = registry
        self.client = client
        self.guard = guard
        self.max_rows = max_rows

    def has_datasource(self, datasource_id: str) -> bool:
        return self.registry.has(datasource_id)

    async def run_select(
        self, datasource_id: str, sql: str, max_rows: int | None = None
    ) -> TableData:
        spec = self.registry.get(datasource_id)
        # Read the SQL the way this data source's engine does; raises SafetyViolation before
        # anything leaves the process.
        self.guard.validate(sql, dialect=spec.dialect)
        limit = min(max_rows or self.max_rows, self.max_rows)
        data = await self.client.call_tool(spec, "run_select", {"sql": sql, "max_rows": limit})
        try:
            return TableData(
                columns=data["columns"], rows=data["rows"], truncated=bool(data.get("truncated"))
            )
        except KeyError as exc:
            raise MCPToolError(f"run_select response missing {exc}") from exc

    async def list_tables(self, datasource_id: str) -> list[str]:
        data = await self.client.call_tool(self.registry.get(datasource_id), "list_tables")
        return [str(t) for t in data.get("tables", [])]

    async def describe_table(self, datasource_id: str, table: str) -> dict[str, Any]:
        return await self.client.call_tool(
            self.registry.get(datasource_id), "describe_table", {"table": table}
        )
