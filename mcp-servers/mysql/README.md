# MySQL MCP server (reference)

A small, read-only [MCP](https://modelcontextprotocol.io) server over stdio that DataLake
Canvas uses as its reference MySQL data source.

| Tool | Arguments | Returns |
| --- | --- | --- |
| `list_tables` | – | `{"tables": ["orders", "other_db.events", ...]}` |
| `describe_table` | `table` (`schema.table` for tables outside `MYSQL_DATABASE`) | `{"table", "columns": [{"name","type","nullable"}]}` |
| `run_select` | `sql`, `max_rows` (default 1000, max 10 000) | `{"columns", "rows", "truncated"}` |

## Requirements

* **MySQL 8.0 or later** (tested on 8.0). MariaDB is not supported. MySQL 5.7 is untested.
* `MAX_EXECUTION_TIME` needs 5.7.8+, CTEs (`WITH`) need 8.0, and `VALUES` must be written as
  `VALUES ROW(...)` (8.0.19+).

## Configuration

| Variable | Meaning |
| --- | --- |
| `MYSQL_HOST` | Server host, default `localhost` |
| `MYSQL_PORT` | Server port, default `3306` |
| `MYSQL_USER` | User name (required) |
| `MYSQL_PASSWORD` | Password (required, but may be empty) |
| `MYSQL_DATABASE` | Default database (required) |
| `MYSQL_STATEMENT_TIMEOUT_MS` | Statement timeout, default `30000`, must be at least 1 |

The example config references all five variables, so set all of them when you use it (an
undefined variable stops the backend at startup). The defaults for host and port apply only when
you run the server standalone.

## Safety model

* Every connection runs `START TRANSACTION READ ONLY` and sets `MAX_EXECUTION_TIME`
  (`MYSQL_STATEMENT_TIMEOUT_MS`, default 30 s).
* `run_select` accepts only statements starting with `SELECT`, `WITH` or `VALUES`.
* Multi-statement support is off, so `SELECT 1; DELETE ...` is a syntax error.
* Locking reads (`SELECT ... FOR UPDATE`) are rejected by the read-only transaction.

### Known limits

* A read-only transaction does **not** stop server-side file writes such as
  `SELECT ... INTO OUTFILE`. Use a MySQL user without the `FILE` privilege and keep
  `secure_file_priv` restrictive. (The backend's SQL guard also blocks `INTO`.)
* Named locks (`GET_LOCK`) are allowed; they are released when the connection closes.
* The default TLS connection encrypts traffic but does not verify the server certificate, so
  prefer a trusted network.
* When a result is cut at `max_rows`, the connection is closed without reading the rest; the
  server stops the query shortly afterwards (at the latest at the statement timeout).
* **Always connect with a `SELECT`-only account.** The guard and the read-only transaction are
  defense in depth; the account's grants are the guarantee.

## Behavior notes

* Tables in `MYSQL_DATABASE` are listed by bare name, others as `schema.table`. Only tables the
  user has privileges on are visible.
* Table names containing a dot or backticks are not supported.
* `DECIMAL` values are returned as floats; `JSON` and `SET` columns as strings; BLOBs as
  `"<N bytes>"`.
* `describe_table` returns short type names (`data_type`): `decimal`, not `decimal(10,2)`.
* Result column names can repeat (for example `SELECT c.id, o.id ...` gives `["id", "id"]`).

## Run it standalone

```bash
pip install -r requirements.txt
export MYSQL_HOST=localhost MYSQL_PORT=3306 MYSQL_USER=readonly_user
export MYSQL_PASSWORD='<password>' MYSQL_DATABASE=mydb
python server.py            # speaks MCP over stdio
```

`requirements.txt` installs PyMySQL with the `rsa` extra: older PyMySQL versions, or servers
without TLS, need the `cryptography` package for MySQL 8's default `caching_sha2_password` login.

Register it with DataLake Canvas by adding an entry to `config/datasources.json`
(see [`config/datasources.mysql.example.json`](../../config/datasources.mysql.example.json)).
Credentials are read from the environment, never from the file.

### Docker

The reference Docker image installs only the PostgreSQL driver, and this is not changed in the
repo yet. To use MySQL with `docker compose`, add `PyMySQL[rsa]` to the `pip install` line in
`backend/Dockerfile`, set `DLC_DATASOURCES_FILE` to the MySQL example config and pass the
`MYSQL_*` variables to the backend service. Alternatively, run the backend locally.

## Running the tests

The unit tests in `backend/tests/test_mysql_server.py` use a fake driver and need neither
PyMySQL nor a database. The opt-in integration tests run against a real server when
`MYSQL_TEST_HOST`, `MYSQL_TEST_USER`, `MYSQL_TEST_PASSWORD` and `MYSQL_TEST_DATABASE` are set
(optionally `MYSQL_TEST_PORT` and `MYSQL_TEST_TABLE`) and PyMySQL is installed:

```bash
pytest backend/tests/test_mysql_server.py -q -rs
```
