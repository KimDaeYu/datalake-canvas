"""Reference MCP server: read-only MySQL access for DataLake Canvas.

Tools (all return JSON objects):
  list_tables()                      -> {"tables": ["orders", "analytics.events", ...]}
  describe_table(table)              -> {"table": ..., "columns": [{"name", "type", "nullable"}]}
  run_select(sql, max_rows=1000)     -> {"columns": [...], "rows": [[...]], "truncated": bool}

Configuration (environment):
  MYSQL_HOST                  server host, default localhost
  MYSQL_PORT                  server port, default 3306
  MYSQL_USER                  user name (required)
  MYSQL_PASSWORD              password (required; may be empty)
  MYSQL_DATABASE              default database (required)
  MYSQL_STATEMENT_TIMEOUT_MS  statement timeout, default 30000

Safety: every query runs inside a READ ONLY transaction, so even a query that slips past the
checks below cannot modify data. Use a MySQL user with SELECT-only grants too.
PyMySQL is imported lazily so the pure helpers can be tested without it installed.
Run over stdio:  python server.py
"""

from __future__ import annotations

import datetime as dt
import decimal
import os
import re
import uuid
from contextlib import contextmanager, suppress
from typing import Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("datalake-mysql")

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


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is not set for this MCP server")
    return value


@contextmanager
def _connection():
    import pymysql  # lazy: keeps the helpers above importable without PyMySQL

    user = _required_env("MYSQL_USER")
    database = _required_env("MYSQL_DATABASE")
    password = os.environ.get("MYSQL_PASSWORD")
    if password is None:  # an empty password is allowed, an unset one is not
        raise RuntimeError("MYSQL_PASSWORD is not set for this MCP server")
    host = os.environ.get("MYSQL_HOST", "localhost")
    port = int(os.environ.get("MYSQL_PORT", "3306"))
    timeout_ms = int(os.environ.get("MYSQL_STATEMENT_TIMEOUT_MS", "30000"))
    if timeout_ms < 1:  # MAX_EXECUTION_TIME = 0 would silently disable the timeout
        raise RuntimeError("MYSQL_STATEMENT_TIMEOUT_MS must be at least 1")

    conn = pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        charset="utf8mb4",
        autocommit=False,
        connect_timeout=10,
    )
    try:
        with conn.cursor() as cur:
            # MAX_EXECUTION_TIME only applies to SELECT statements, which is all we run.
            # READ ONLY still permits writes to TEMPORARY tables, so use a SELECT-only user too.
            cur.execute("SET SESSION TRANSACTION READ ONLY")
            try:
                cur.execute(f"SET SESSION MAX_EXECUTION_TIME = {timeout_ms}")  # int: no injection
            except pymysql.MySQLError as exc:
                raise RuntimeError(
                    "Could not set MAX_EXECUTION_TIME; the server may not support it "
                    "(MySQL 5.7.8+ or 8.0 is required; MariaDB is not supported)"
                ) from exc
            cur.execute("START TRANSACTION READ ONLY")
        yield conn
    finally:
        # Nothing to commit. A failed rollback must not mask the original error, and the
        # server discards the transaction when the connection closes anyway. run_select may
        # have closed the connection already: rollback() then raises InterfaceError and a
        # second close() raises Error("Already closed"), both MySQLError subclasses.
        with suppress(pymysql.MySQLError):
            conn.rollback()
        with suppress(pymysql.MySQLError):
            conn.close()


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, dt.datetime | dt.date | dt.time):
        return value.isoformat()
    if isinstance(value, dt.timedelta):  # PyMySQL returns TIME columns as timedelta
        return str(value)
    if isinstance(value, set):  # SET columns
        return sorted(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, bytes | bytearray | memoryview):
        return f"<{len(bytes(value))} bytes>"
    return str(value)


def _text(value: Any) -> str:
    """information_schema columns may come back as bytes on some MySQL versions."""
    return value.decode("utf-8") if isinstance(value, bytes | bytearray) else str(value)


def _format_table_name(default_db: str, schema: str, name: str) -> str:
    return name if schema == default_db else f"{schema}.{name}"


def _split_table_name(table: str, default_db: str) -> tuple[str, str]:
    schema, _, name = table.rpartition(".")
    return schema or default_db, name


@mcp.tool()
def list_tables() -> dict[str, Any]:
    """List tables and views the connected user can see (non-system schemas).

    Only tables the user has privileges on are included. Tables in MYSQL_DATABASE are listed
    by bare name, others as 'schema.table'.
    """
    with _connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT DATABASE()")
        default_db = _text(cur.fetchone()[0])
        cur.execute(
            """
            SELECT table_schema, table_name FROM information_schema.tables
            WHERE table_type IN ('BASE TABLE', 'VIEW')
              AND table_schema NOT IN ('mysql', 'information_schema', 'performance_schema', 'sys')
            ORDER BY table_schema, table_name
            """
        )
        rows = cur.fetchall()
    return {"tables": [_format_table_name(default_db, _text(s), _text(t)) for s, t in rows]}


@mcp.tool()
def describe_table(table: str) -> dict[str, Any]:
    """Describe a table's columns. Use 'schema.table' for tables outside MYSQL_DATABASE."""
    with _connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT DATABASE()")
        schema, name = _split_table_name(table, _text(cur.fetchone()[0]))
        cur.execute(
            """
            SELECT column_name, data_type, is_nullable FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s ORDER BY ordinal_position
            """,
            (schema, name),
        )
        rows = cur.fetchall()
    if not rows:
        raise ValueError(f"Unknown table {table!r}")
    return {
        "table": table,
        "columns": [
            {"name": _text(n), "type": _text(t), "nullable": _text(nl) == "YES"}
            for n, t, nl in rows
        ],
    }


@mcp.tool()
def run_select(sql: str, max_rows: int = 1000) -> dict[str, Any]:
    """Run a read-only SELECT and return at most max_rows rows."""
    import pymysql.cursors

    max_rows = max(1, min(int(max_rows), 10_000))
    sql = _require_read_only_start(sql)
    # Not wrapped in a derived table: MySQL rejects duplicate column names there (e.g. a join
    # returning two `id` columns), so the user's SQL runs as is.
    with _connection() as conn:
        with conn.cursor() as cur:
            # Server-side backstop only: an explicit LIMIT in the query overrides it, so the
            # client-side cap below is the authoritative one.
            cur.execute(f"SET SESSION sql_select_limit = {max_rows + 1}")  # int: no injection
        cur = conn.cursor(pymysql.cursors.SSCursor)  # not a context manager: close() drains
        cur.execute(sql)
        columns = [d[0] for d in cur.description or []]
        rows = cur.fetchmany(max_rows + 1)
        truncated = len(rows) > max_rows
        if truncated:
            # More rows may still be streaming, and cursor.close() / rollback() would read all
            # of them first. Closing the connection discards them instead. Clearing the flag
            # stops MySQLResult.__del__ from trying to drain the closed socket later (which
            # prints an "Exception ignored" traceback to stderr). This touches a PyMySQL
            # internal, checked against PyMySQL 1.1.0 and 1.2.x; if the attribute ever
            # disappears the only effect is that stderr message, never a wrong result.
            result = getattr(conn, "_result", None)
            if result is not None:
                result.unbuffered_active = False
            conn.close()
        else:
            cur.close()  # result fully read; nothing left to drain
    return {
        "columns": columns,
        "rows": [[_jsonable(v) for v in row] for row in rows[:max_rows]],
        "truncated": truncated,
    }


if __name__ == "__main__":
    mcp.run()  # stdio transport
