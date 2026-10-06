# PostgreSQL MCP server (reference)

A small, read-only [MCP](https://modelcontextprotocol.io) server over stdio that DataLake
Canvas uses as its reference PostgreSQL data source.

| Tool | Arguments | Returns |
| --- | --- | --- |
| `list_tables` | – | `{"tables": ["orders", ...]}` |
| `describe_table` | `table` (`schema.table` for non-public) | `{"table", "columns": [{"name","type","nullable"}]}` |
| `run_select` | `sql`, `max_rows` (default 1000, max 10 000) | `{"columns", "rows", "truncated"}` |

## Safety model

* Connections are opened as `READ ONLY` transactions with a statement timeout
  (`POSTGRES_STATEMENT_TIMEOUT_MS`, default 30 s).
* `run_select` accepts only statements starting with `SELECT`, `WITH` or `VALUES`.
* **You should still connect with a role that only has `SELECT` grants.**

## Run it standalone

```bash
pip install -r requirements.txt
export POSTGRES_DSN="postgresql://readonly_user:<password>@localhost:5432/mydb"
python server.py            # speaks MCP over stdio
```

Register it with DataLake Canvas by adding an entry to `config/datasources.json`
(see [`config/datasources.postgres.example.json`](../../config/datasources.postgres.example.json)).
The DSN is read from the environment, never from the file.
