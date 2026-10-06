"""MCP server: read-only SQLite access, used for the bundled demo dataset.

Exposes the same three tools as the PostgreSQL reference server (see
docs/data-sources.md for the contract): list_tables, describe_table, run_select.

Configuration (environment):
  SQLITE_DB_PATH   path to the database file (required)

The file is opened with ``mode=ro`` and ``PRAGMA query_only=ON``; queries are also aborted
after SQLITE_TIMEOUT_SECONDS (default 30).
"""

from __future__ import annotations

import os
import re
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("datalake-sqlite")

_LEADING_NOISE = re.compile(r"\s+|--[^\n]*(\n|$)|/\*.*?\*/", re.DOTALL)
_READ_START = re.compile(r"(select|with|values)\b", re.IGNORECASE)


def _require_read_only_start(sql: str) -> None:
    pos = 0
    while (m := _LEADING_NOISE.match(sql, pos)) and m.end() > pos:
        pos = m.end()
    if not _READ_START.match(sql, pos):
        raise ValueError("Only SELECT / WITH / VALUES queries are allowed")


def _connect() -> sqlite3.Connection:
    path = os.environ.get("SQLITE_DB_PATH")
    if not path:
        raise RuntimeError("SQLITE_DB_PATH is not set for this MCP server")
    db = Path(path).resolve()
    if not db.exists():
        raise FileNotFoundError(
            f"{db} does not exist. Build it with: python examples/demo-data/build_demo_db.py"
        )
    conn = sqlite3.connect(f"{db.as_uri()}?mode=ro", uri=True)
    conn.execute("PRAGMA query_only = ON")
    deadline = time.monotonic() + float(os.environ.get("SQLITE_TIMEOUT_SECONDS", "30"))
    conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10_000)
    return conn


def _jsonable(value: Any) -> Any:
    return f"<{len(value)} bytes>" if isinstance(value, bytes) else value


@mcp.tool()
def list_tables() -> dict[str, Any]:
    """List tables and views in the database."""
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'view') "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
    return {"tables": [r[0] for r in rows]}


@mcp.tool()
def describe_table(table: str) -> dict[str, Any]:
    """Describe a table's columns."""
    with closing(_connect()) as conn:
        # Table-valued function: the name is a bound parameter, not interpolated.
        rows = conn.execute(
            'SELECT name, type, "notnull" FROM pragma_table_info(?) ORDER BY cid', (table,)
        ).fetchall()
    if not rows:
        raise ValueError(f"Unknown table {table!r}")
    return {
        "table": table,
        "columns": [{"name": n, "type": t, "nullable": not nn} for n, t, nn in rows],
    }


@mcp.tool()
def run_select(sql: str, max_rows: int = 1000) -> dict[str, Any]:
    """Run a read-only SELECT and return at most max_rows rows."""
    max_rows = max(1, min(int(max_rows), 10_000))
    _require_read_only_start(sql)
    with closing(_connect()) as conn:
        cur = conn.execute(sql)
        columns = [d[0] for d in cur.description or []]
        rows = cur.fetchmany(max_rows + 1)
    return {
        "columns": columns,
        "rows": [[_jsonable(v) for v in row] for row in rows[:max_rows]],
        "truncated": len(rows) > max_rows,
    }


if __name__ == "__main__":
    mcp.run()  # stdio transport
