# SQLite MCP server

Read-only MCP server (stdio) over a SQLite file, exposing the same `list_tables`,
`describe_table` and `run_select` tools as the [PostgreSQL reference server](../postgres).
It powers the bundled demo dataset and depends only on the `mcp` package.

```bash
SQLITE_DB_PATH=examples/demo-data/demo.db python server.py
```
