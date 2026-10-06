# Adding a data source

Every data source is an [MCP](https://modelcontextprotocol.io) server launched over stdio. The
backend never talks to databases directly.

## 1. The tool contract

A server must expose these tools and return JSON objects:

| Tool | Arguments | Result |
| --- | --- | --- |
| `list_tables` | – | `{"tables": ["orders", ...]}` |
| `describe_table` | `table: str` | `{"table": "orders", "columns": [{"name": "id", "type": "INTEGER", "nullable": false}]}` |
| `run_select` | `sql: str`, `max_rows: int` | `{"columns": ["a"], "rows": [[1]], "truncated": false}` |

Values in `rows` must be JSON-serializable (stringify dates, decimals, UUIDs). Enforce read-only
access **in the server** (read-only connection / role), not only in the backend. See
[`mcp-servers/postgres/server.py`](../mcp-servers/postgres/server.py),
[`mcp-servers/mysql/server.py`](../mcp-servers/mysql/server.py) and
[`mcp-servers/sqlite/server.py`](../mcp-servers/sqlite/server.py) for short examples built on the
official `mcp` SDK (`FastMCP`). [`config/datasources.mysql.example.json`](../config/datasources.mysql.example.json)
shows how to register the MySQL one.

## 2. Register it

Add an entry to `config/datasources.json` (or a file named by `DLC_DATASOURCES_FILE`):

```json
{
  "id": "my-warehouse",
  "name": "My warehouse",
  "dialect": "postgresql",
  "command": "python",
  "args": ["${DLC_ROOT}/mcp-servers/postgres/server.py"],
  "env": { "POSTGRES_DSN": "${MY_WAREHOUSE_DSN}" }
}
```

* `${VAR}` is expanded from `DLC_ROOT`, `DLC_DATA_DIR`, then the process environment. A missing
  variable fails startup loudly. Put credentials in the environment, never in this file.
* `"command": "python"` resolves to the backend's own interpreter.
* `dialect` is passed to the LLM so it writes SQL for the right engine.
* Only the variables in `env` (plus a minimal default set such as `PATH`) reach the server process.

Restart the backend; the source appears in the UI's data source pickers.

## 3. Trying the PostgreSQL reference server

```bash
echo 'POSTGRES_PASSWORD=choose-something' >> .env
docker compose -f docker-compose.yml -f docker-compose.postgres.yml up --build
```

This adds a throwaway demo Postgres loaded with the same synthetic dataset and registers it as
`demo-postgres`.
