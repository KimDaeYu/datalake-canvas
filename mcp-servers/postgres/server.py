"""Reference MCP server: read-only PostgreSQL access for DataLake Canvas.

Tools (all return JSON objects):
  list_tables()                      -> {"tables": ["orders", "analytics.events", ...]}
  describe_table(table)              -> {"table": ..., "columns": [{"name", "type", "nullable"}]}
  run_select(sql, max_rows=1000)     -> {"columns": [...], "rows": [[...]], "truncated": bool}

Configuration (environment):
  POSTGRES_DSN                  libpq connection string / URL (required)
  POSTGRES_STATEMENT_TIMEOUT_MS statement timeout, default 30000

Safety: every connection is opened as a READ ONLY transaction, so even a query that slips
past the checks below cannot modify data. Use a database role with SELECT-only grants too.
Run over stdio:  python server.py
"""

from __future__ import annotations

import datetime as dt
import decimal
import os
import re
import uuid
from contextlib import contextmanager
from typing import Any

import psycopg
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("datalake-postgres")

_LEADING_NOISE = re.compile(r"\s+|--[^\n]*(\n|$)|/\*.*?\*/", re.DOTALL)
_READ_START = re.compile(r"(select|with|values)\b", re.IGNORECASE)


def _require_read_only_start(sql: str) -> str:
    """Cheap pre-check; the read-only transaction is what actually enforces safety."""
    pos = 0
    while (m := _LEADING_NOISE.match(sql, pos)) and m.end() > pos:
        pos = m.end()
    if not _READ_START.match(sql, pos):
        raise ValueError("Only SELECT / WITH / VALUES queries are allowed")
    return sql.strip().rstrip(";").rstrip()


@contextmanager
def _connection():
    dsn = os.environ.get("POSTGRES_DSN")
    if not dsn:
        raise RuntimeError("POSTGRES_DSN is not set for this MCP server")
    timeout_ms = int(os.environ.get("POSTGRES_STATEMENT_TIMEOUT_MS", "30000"))
    with psycopg.connect(dsn, autocommit=False) as conn:
        conn.read_only = True
        conn.execute(f"SET LOCAL statement_timeout = {timeout_ms}")  # int-formatted: no injection
        yield conn
        conn.rollback()  # nothing to commit; leave no transaction open


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, dt.datetime | dt.date | dt.time):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, bytes | memoryview):
        return f"<{len(bytes(value))} bytes>"
    return str(value)


@mcp.tool()
def list_tables() -> dict[str, Any]:
    """List tables and views the connected role can see (non-system schemas)."""
    with _connection() as conn:
        rows = conn.execute(
            """
            SELECT table_schema, table_name FROM information_schema.tables
            WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
            ORDER BY table_schema, table_name
            """
        ).fetchall()
    return {"tables": [t if s == "public" else f"{s}.{t}" for s, t in rows]}


@mcp.tool()
def describe_table(table: str) -> dict[str, Any]:
    """Describe a table's columns. Use 'schema.table' for non-public schemas."""
    schema, _, name = table.rpartition(".")
    schema = schema or "public"
    with _connection() as conn:
        rows = conn.execute(
            """
            SELECT column_name, data_type, is_nullable FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s ORDER BY ordinal_position
            """,
            (schema, name),
        ).fetchall()
    if not rows:
        raise ValueError(f"Unknown table {table!r}")
    return {
        "table": table,
        "columns": [{"name": n, "type": t, "nullable": nl == "YES"} for n, t, nl in rows],
    }


@mcp.tool()
def run_select(sql: str, max_rows: int = 1000) -> dict[str, Any]:
    """Run a read-only SELECT and return at most max_rows rows."""
    max_rows = max(1, min(int(max_rows), 10_000))
    inner = _require_read_only_start(sql)
    # Wrap so the database applies the LIMIT; newlines protect against a trailing `--` comment.
    wrapped = f"SELECT * FROM (\n{inner}\n) AS _dlc LIMIT {max_rows + 1}"
    with _connection() as conn:
        cur = conn.execute(wrapped)
        columns = [d.name for d in cur.description or []]
        rows = cur.fetchall()
    truncated = len(rows) > max_rows
    return {
        "columns": columns,
        "rows": [[_jsonable(v) for v in row] for row in rows[:max_rows]],
        "truncated": truncated,
    }


if __name__ == "__main__":
    mcp.run()  # stdio transport
