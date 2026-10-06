"""Thin wrapper around the official MCP Python SDK (stdio transport).

Each call spawns the configured server, runs one tool and tears it down again. That costs
a process start per call, but it keeps the lifecycle trivial and avoids anyio cancel-scope
problems from sharing a long-lived session across FastAPI request tasks. A pooled
client can replace this class without touching callers.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class MCPServerSpec(BaseModel):
    """How to launch one MCP server that exposes a database."""

    id: str = Field(min_length=1)
    name: str
    description: str = ""
    dialect: str = "sql"
    command: str
    args: list[str] = Field(default_factory=list)
    # Extra environment for the server process. Only these variables (plus the SDK's
    # small default allow-list such as PATH) reach the subprocess.
    env: dict[str, str] = Field(default_factory=dict)


class MCPToolError(RuntimeError):
    """The server could not be reached or the tool reported an error."""


class MCPClient:
    def __init__(self, timeout: float = 30.0) -> None:
        self.timeout = timeout

    async def call_tool(
        self, spec: MCPServerSpec, tool: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Call ``tool`` on the server and return its structured (dict) result."""
        params = StdioServerParameters(command=spec.command, args=spec.args, env=spec.env)
        try:
            async with (
                asyncio.timeout(self.timeout),
                stdio_client(params) as (read, write),
                ClientSession(read, write) as session,
            ):
                await session.initialize()
                result = await session.call_tool(tool, arguments or {})
        except TimeoutError as exc:
            raise MCPToolError(f"{spec.id}.{tool} timed out after {self.timeout}s") from exc
        except MCPToolError:
            raise
        except Exception as exc:  # SDK/transport errors, incl. ExceptionGroup from anyio
            logger.exception("MCP call %s.%s failed", spec.id, tool)
            raise MCPToolError(f"{spec.id}.{tool} failed: {exc}") from exc

        text = " ".join(c.text for c in result.content if getattr(c, "type", "") == "text")
        if result.isError:
            raise MCPToolError(text or f"{spec.id}.{tool} reported an error")
        if result.structuredContent is not None:
            return dict(result.structuredContent)
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise MCPToolError(f"{spec.id}.{tool} returned non-JSON output") from exc
        if not isinstance(parsed, dict):
            raise MCPToolError(
                f"{spec.id}.{tool} returned {type(parsed).__name__}, expected object"
            )
        return parsed
