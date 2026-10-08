"""Tests for the MySQL MCP server (mcp-servers/mysql/server.py).

Pure helpers and the connection/run_select logic are tested against a fake ``pymysql`` module,
so neither PyMySQL nor a database is needed. The integration tests at the bottom spawn the real
server over stdio and only run when MYSQL_TEST_HOST, MYSQL_TEST_USER, MYSQL_TEST_PASSWORD and
MYSQL_TEST_DATABASE are set (and PyMySQL is installed).
"""

import datetime as dt
import decimal
import importlib.util
import os
import sys
import time
import types
import uuid

import pytest

from datalake_canvas.mcp_client import MCPClient, MCPServerSpec, MCPToolError
from tests.conftest import REPO_ROOT

SERVER_PATH = REPO_ROOT / "mcp-servers" / "mysql" / "server.py"


@pytest.fixture(scope="module")
def server():
    spec = importlib.util.spec_from_file_location("dlc_mysql_server", SERVER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- Pure helpers --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT 1", "SELECT 1"),
        ("  select 1;", "select 1"),
        ("WITH x AS (SELECT 1) SELECT * FROM x", "WITH x AS (SELECT 1) SELECT * FROM x"),
        ("VALUES ROW(1)", "VALUES ROW(1)"),
        ("-- c\nSELECT 1", "-- c\nSELECT 1"),
        ("/* c */ SELECT 1", "/* c */ SELECT 1"),
    ],
)
def test_require_read_only_start_accepts(server, sql, expected):
    assert server._require_read_only_start(sql) == expected


@pytest.mark.parametrize(
    "sql",
    [
        "",
        "   ",
        "DELETE FROM t",
        "INSERT INTO t VALUES (1)",
        "/* SELECT */ DELETE FROM t",
        "SELECTED 1",
        "WITHDRAW 1",
    ],
)
def test_require_read_only_start_rejects(server, sql):
    with pytest.raises(ValueError, match="Only SELECT"):
        server._require_read_only_start(sql)


# Raw strings below: the SQL text contains exactly one backslash where r"...\'..." shows one.
@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1",
        "SELECT 'into outfile' AS s",
        'SELECT "into" AS s',
        "SELECT `into` FROM t",
        "SELECT into_x, x_into, into1 FROM t",
        "SELECT 1 -- INTO OUTFILE '/x'",
        "SELECT 1 --",  # comment at the very end of the input
        "SELECT 1 # INTO OUTFILE '/x'",
        "SELECT /* INTO */ 1",
        "SELECT 'it''s into' AS s",
        r"SELECT 'a\'b' AS s",  # backslash-escaped quote, valid in the default sql_mode
        # Terminates only when backslashes are NOT escapes; allowed because the other reading
        # (unterminated) cannot be how MySQL parses it.
        r"SELECT 'C:\dir\' AS p",
        "SELECT 1--1",  # no space after the dashes: arithmetic, no comment, no INTO
    ],
)
def test_reject_into_allows(server, sql):
    server._reject_into(sql)


INTO_MSG = "INTO is not allowed"
EXEC_MSG = "Executable comments"
HINT_MSG = "Optimizer hints"


@pytest.mark.parametrize(
    ("sql", "message"),
    [
        ("SELECT 1 INTO OUTFILE '/tmp/x'", INTO_MSG),
        ("select 1 into dumpfile '/tmp/x'", INTO_MSG),
        ("SELECT 1\nINTO\tOUTFILE '/tmp/x'", INTO_MSG),
        ("SELECT * FROM t INTO OUTFILE '/tmp/x'", INTO_MSG),
        ("SELECT 1 INTO /* c */ OUTFILE '/tmp/x'", INTO_MSG),
        ("SELECT 1 /* c */ INTO OUTFILE '/tmp/x'", INTO_MSG),
        ("SELECT 1 -- c\nINTO OUTFILE '/tmp/x'", INTO_MSG),  # a line comment ends at the newline
        ("SELECT 1 # c\nINTO OUTFILE '/tmp/x'", INTO_MSG),
        ("WITH x AS (SELECT 1) SELECT * FROM x INTO OUTFILE '/tmp/x'", INTO_MSG),
        ("SELECT 1 UNION SELECT 2 INTO OUTFILE '/tmp/x'", INTO_MSG),
        # Deliberately blocked (text scan, see _reject_into): backtick-quote such names instead.
        ("SELECT 1 INTO @v", INTO_MSG),
        ("SELECT t.into FROM t", INTO_MSG),
        ("SELECT @into", INTO_MSG),
        # MySQL-specific lexing: backslash escapes, "--" needs a following
        # space, "#" comments and executable comments
        # \' is an escaped quote in MySQL, so INTO is live; the final "-- " starts a comment
        (r"SELECT 'a\'' INTO OUTFILE '/tmp/x' -- '", INTO_MSG),
        # "--1" is arithmetic in MySQL, not a comment
        ("SELECT 1 --1 INTO OUTFILE '/tmp/x'", INTO_MSG),
        # MySQL executes the content of /*! ... */
        ("SELECT 1 /*!50000 INTO OUTFILE '/tmp/x' */", EXEC_MSG),
        # MySQL executes the content of /*! ... */
        ("SELECT 1 /*! INTO OUTFILE '/tmp/x' */", EXEC_MSG),
        # MariaDB form of an executable comment
        ("SELECT 1 /*M!100100 INTO OUTFILE '/tmp/x' */", EXEC_MSG),
        ("/*!50000 SELECT 1 */ SELECT 2", EXEC_MSG),  # a leading executable comment
        # With NO_BACKSLASH_ESCAPES the string ends after the backslash and INTO is live.
        (r"SELECT 'a\' INTO OUTFILE '/tmp/x'", INTO_MSG),
        # Documented false positive: the conservative no-escapes reading sees INTO outside the
        # string. Write '' instead of \' to keep such a query.
        (r"SELECT 'O\'Brien went into the shop' AS s", INTO_MSG),
    ],
)
def test_reject_into_blocks(server, sql, message):
    with pytest.raises(ValueError, match=message):
        server._reject_into(sql)


# sql_mode can change where a quoted token ends, so the scan reads each statement twice (backslash
# as an escape, and not). These inputs need the reading that matches the server's mode: each one is
# invisible to one reading and caught by the other.
# ANSI_QUOTES: "..." is an identifier and a backslash inside it is NOT an escape.
ANSI_QUOTES_SQL = r"""SELECT "a\" INTO OUTFILE '/tmp/x' -- " """
# NO_BACKSLASH_ESCAPES: a backslash inside '...' is an ordinary character.
NO_BACKSLASH_SQL = r"SELECT 'a\' INTO OUTFILE '/tmp/x' -- '"


@pytest.mark.parametrize("sql", [ANSI_QUOTES_SQL, NO_BACKSLASH_SQL])
def test_reject_into_catches_sql_mode_dependent_quoting(server, sql):
    with pytest.raises(ValueError, match=INTO_MSG):
        server._reject_into(sql)


@pytest.mark.parametrize("sql", [ANSI_QUOTES_SQL, NO_BACKSLASH_SQL])
def test_each_single_reading_misses_a_sql_mode_case(server, sql):
    # Regression guard for the double scan: reading with backslash escapes hides the INTO inside
    # what it takes for a string, the reading without escapes finds it. Scanning only once (for
    # example after pinning NO_BACKSLASH_ESCAPES in the session) would reopen the ANSI_QUOTES case.
    assert server._scan(sql, True) is None
    assert server._scan(sql, False) == "INTO"


# Optimizer hints can lift MAX_EXECUTION_TIME for one statement, so any /*+ ... */ is rejected.
@pytest.mark.parametrize(
    "sql",
    [
        "SELECT /*+ NO_ICP(t) */ 1 FROM t",
        "SELECT /*+ SET_VAR(max_execution_time=0) */ * FROM t",
        "SELECT /*+ MAX_EXECUTION_TIME(1000) */ * FROM t",
        "SELECT/*+ x */1",
        "/*+ x */ SELECT 1",
        "SELECT * FROM (SELECT /*+ MAX_EXECUTION_TIME(0) */ a FROM t) AS s",
        "WITH /*+ x */ c AS (SELECT 1) SELECT * FROM c",
        "WITH c AS (SELECT /*+ SET_VAR(max_execution_time=0) */ 1) SELECT * FROM c",
        "SELECT /*+ x",  # unterminated: rejected as a hint before the missing */ matters
        # Only the reading without backslash escapes ends the string before the hint.
        r"SELECT 'a\' /*+ MAX_EXECUTION_TIME(0) */ 1 -- '",
    ],
)
def test_reject_into_blocks_optimizer_hints(server, sql):
    with pytest.raises(ValueError, match=HINT_MSG):
        server._reject_into(sql)


def test_optimizer_hint_message_matches_backend_guard(server):
    with pytest.raises(ValueError) as exc_info:
        server._reject_into("SELECT /*+ SET_VAR(max_execution_time=0) */ 1")
    assert str(exc_info.value) == "Optimizer hints /*+ ... */ are not allowed"


@pytest.mark.parametrize(
    ("sql", "with_escapes", "without_escapes"),
    [
        (r"SELECT 'a\' /*+ x */ 1 -- '", None, "HINT"),
        (r"""SELECT "a\" /*+ x */ 1 -- " """, None, "HINT"),  # ANSI_QUOTES identifier
    ],
)
def test_hint_found_by_one_reading_only(server, sql, with_escapes, without_escapes):
    assert server._scan(sql, True) == with_escapes
    assert server._scan(sql, False) == without_escapes


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT '/*+ MAX_EXECUTION_TIME(0) */' AS s",
        "SELECT `/*+ x */` FROM t",
        'SELECT "/*+ x */" AS s',
        "SELECT 1 -- /*+ MAX_EXECUTION_TIME(0) */",
        "SELECT 1 # /*+ MAX_EXECUTION_TIME(0) */",
        "SELECT /* +x */ 1",  # not contiguous: an ordinary comment
        "SELECT /* note /*+ x */ 1",  # "/*+" inside an ordinary comment opens nothing
    ],
)
def test_reject_into_allows_hint_text_outside_hints(server, sql):
    server._reject_into(sql)


@pytest.mark.parametrize("sql", ["SELECT 'abc", "SELECT `abc", 'SELECT "abc', "SELECT 1 /* x"])
def test_reject_into_unterminated(server, sql):
    with pytest.raises(ValueError, match=r"^Unterminated"):
        server._reject_into(sql)


UID = uuid.UUID("12345678-1234-5678-1234-567812345678")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (decimal.Decimal("1.5"), 1.5),
        (dt.datetime(2024, 1, 2, 3, 4, 5), "2024-01-02T03:04:05"),
        (dt.date(2024, 1, 2), "2024-01-02"),
        (dt.time(3, 4, 5), "03:04:05"),
        (dt.timedelta(hours=1, minutes=2, seconds=3), "1:02:03"),  # PyMySQL's TIME type
        (b"abc", "<3 bytes>"),
        (bytearray(b"ab"), "<2 bytes>"),
        ({"b", "a"}, ["a", "b"]),  # SET columns
        (UID, "12345678-1234-5678-1234-567812345678"),
        (None, None),
        (True, True),
        (7, 7),
        (1.5, 1.5),
        ("x", "x"),
    ],
)
def test_jsonable(server, value, expected):
    result = server._jsonable(value)
    assert result == expected and type(result) is type(expected)


@pytest.mark.parametrize(("value", "expected"), [(b"varchar", "varchar"), ("int", "int")])
def test_text(server, value, expected):
    assert server._text(value) == expected


@pytest.mark.parametrize(
    ("schema", "name", "expected"),
    [("shop", "orders", "orders"), ("hr", "emp", "hr.emp")],
)
def test_format_table_name(server, schema, name, expected):
    assert server._format_table_name("shop", schema, name) == expected


@pytest.mark.parametrize(
    ("table", "expected"),
    [("orders", ("shop", "orders")), ("hr.emp", ("hr", "emp")), (".orders", ("shop", "orders"))],
)
def test_split_table_name(server, table, expected):
    assert server._split_table_name(table, "shop") == expected


# --- Fake pymysql --------------------------------------------------------------------------


class FakeMySQLError(Exception):
    pass


class FakeError(FakeMySQLError):
    pass


class FakeInterfaceError(FakeMySQLError):
    pass


class FakeSSCursor:
    """Marker class: run_select passes it to conn.cursor()."""


class FakeResult:
    unbuffered_active = True


class FakeCursor:
    def __init__(self, conn, cls):
        self.conn = conn
        self.cls = cls
        self.description = None
        self.last_sql = None

    # Unlike PyMySQL, leaving the block records nothing, so "cursor.close" only shows up when
    # close() is called explicitly (which run_select does on the SSCursor).
    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return None

    def execute(self, sql, params=None):
        self.conn.calls.append(sql)
        self.conn.params.append((sql, params))
        self.last_sql = sql
        if self.conn.fail_on and sql.startswith(self.conn.fail_on):
            raise FakeMySQLError(1193, "Unknown system variable")
        if self.cls is FakeSSCursor:
            self.description = [(name, None) for name in self.conn.columns]

    def fetchone(self):
        return ("shop",) if self.last_sql == "SELECT DATABASE()" else None

    def fetchmany(self, size):
        return self.conn.rows[:size]

    def fetchall(self):
        return self.conn.rows

    def close(self):
        self.conn.calls.append("cursor.close")


class FakeConnection:
    def __init__(self, rows=(), columns=("a",), fail_on=None):
        self.calls: list[str] = []
        self.params: list[tuple[str, object]] = []
        self.rows = [tuple(r) for r in rows]
        self.columns = columns
        self.fail_on = fail_on
        self._result = FakeResult()
        self.closed = False

    def cursor(self, cls=None):
        return FakeCursor(self, cls)

    def rollback(self):
        if self.closed:
            self.calls.append("rollback (closed)")  # record the attempt, then fail like PyMySQL
            raise FakeInterfaceError(0, "")
        self.calls.append("rollback")

    def close(self):
        self.calls.append("close")
        if self.closed:
            raise FakeError("Already closed")
        self.closed = True


MARKERS = {"rollback", "rollback (closed)", "close", "cursor.close"}


def statements(conn):
    return [c for c in conn.calls if c not in MARKERS]


@pytest.fixture
def fake_pymysql(monkeypatch):
    cursors = types.ModuleType("pymysql.cursors")
    cursors.SSCursor = FakeSSCursor
    fake = types.ModuleType("pymysql")
    fake.cursors = cursors
    fake.MySQLError = FakeMySQLError
    fake.Error = FakeError
    fake.InterfaceError = FakeInterfaceError
    fake.connect_kwargs = []
    fake.connection = FakeConnection()

    def connect(**kwargs):
        fake.connect_kwargs.append(kwargs)
        return fake.connection

    fake.connect = connect
    monkeypatch.setitem(sys.modules, "pymysql", fake)
    monkeypatch.setitem(sys.modules, "pymysql.cursors", cursors)
    return fake


@pytest.fixture
def mysql_env(monkeypatch):
    for name in ("MYSQL_HOST", "MYSQL_PORT", "MYSQL_STATEMENT_TIMEOUT_MS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("MYSQL_USER", "reader")
    monkeypatch.setenv("MYSQL_PASSWORD", "")
    monkeypatch.setenv("MYSQL_DATABASE", "shop")


# --- Connection and run_select against the fake ---------------------------------------------


def test_connect_arguments_and_empty_password(server, fake_pymysql, mysql_env):
    server.run_select("SELECT 1")
    [kwargs] = fake_pymysql.connect_kwargs
    assert kwargs["autocommit"] is False
    assert kwargs["charset"] == "utf8mb4"
    assert kwargs["connect_timeout"] == 10
    assert kwargs["password"] == ""
    assert (kwargs["host"], kwargs["port"]) == ("localhost", 3306)
    assert (kwargs["user"], kwargs["database"]) == ("reader", "shop")


def test_statement_order(server, fake_pymysql, mysql_env):
    server.run_select("SELECT a FROM t", max_rows=10)
    assert statements(fake_pymysql.connection) == [
        "SET SESSION TRANSACTION READ ONLY",
        "SET SESSION MAX_EXECUTION_TIME = 30000",
        "START TRANSACTION READ ONLY",
        "SET SESSION sql_select_limit = 11",
        "SELECT a FROM t",
    ]


def test_truncated_closes_connection_without_draining(server, fake_pymysql, mysql_env):
    conn = fake_pymysql.connection = FakeConnection(rows=[(i,) for i in range(4)])
    result = server.run_select("SELECT a FROM t", max_rows=3)

    assert result == {"columns": ["a"], "rows": [[0], [1], [2]], "truncated": True}
    assert "cursor.close" not in conn.calls
    assert conn._result.unbuffered_active is False
    first_rollback = conn.calls.index("rollback (closed)")
    assert conn.calls[:first_rollback].count("close") == 1
    assert "rollback" not in conn.calls  # never rolled back on the open connection
    assert conn.closed


def test_not_truncated_closes_cursor_then_rolls_back(server, fake_pymysql, mysql_env):
    conn = fake_pymysql.connection = FakeConnection(rows=[(1,), (2,)])
    result = server.run_select("SELECT a FROM t", max_rows=3)

    assert result == {"columns": ["a"], "rows": [[1], [2]], "truncated": False}
    assert "cursor.close" in conn.calls
    assert conn.calls[-2:] == ["rollback", "close"]
    assert conn.calls.count("close") == 1


@pytest.mark.parametrize(("max_rows", "limit"), [(0, 2), (50_000, 10_001)])
def test_max_rows_is_clamped(server, fake_pymysql, mysql_env, max_rows, limit):
    server.run_select("SELECT 1", max_rows=max_rows)
    assert f"SET SESSION sql_select_limit = {limit}" in fake_pymysql.connection.calls


def test_write_is_rejected_before_connecting(server, fake_pymysql, mysql_env):
    with pytest.raises(ValueError, match="Only SELECT"):
        server.run_select("DELETE FROM t")
    assert fake_pymysql.connect_kwargs == []


@pytest.mark.parametrize(
    ("sql", "message"),
    [
        ("SELECT 1 INTO OUTFILE '/tmp/x'", "INTO is not allowed"),
        ("SELECT 1 /*!50000 INTO OUTFILE '/tmp/x' */", "Executable comments"),
        ("SELECT /*+ SET_VAR(max_execution_time=0) */ 1", "Optimizer hints"),
        ("SELECT /*+ MAX_EXECUTION_TIME(60000) */ 1", "Optimizer hints"),
    ],
)
def test_into_is_rejected_before_connecting(server, fake_pymysql, mysql_env, sql, message):
    with pytest.raises(ValueError, match=message):
        server.run_select(sql)
    assert fake_pymysql.connect_kwargs == []


def test_into_in_comment_still_runs(server, fake_pymysql, mysql_env):
    sql = "SELECT 1 -- INTO OUTFILE '/tmp/x'"
    conn = fake_pymysql.connection = FakeConnection(rows=[(1,)])
    result = server.run_select(sql)

    assert result == {"columns": ["a"], "rows": [[1]], "truncated": False}
    assert len(fake_pymysql.connect_kwargs) == 1
    assert statements(conn)[-1] == sql


SECRETS = {"MYSQL_USER": "u-s3cret", "MYSQL_PASSWORD": "p-s3cret", "MYSQL_DATABASE": "d-s3cret"}


@pytest.mark.parametrize(
    ("missing", "value"),
    [
        ("MYSQL_USER", None),
        ("MYSQL_USER", ""),
        ("MYSQL_DATABASE", None),
        ("MYSQL_DATABASE", ""),
        ("MYSQL_PASSWORD", None),
    ],
)
def test_missing_required_env(server, fake_pymysql, monkeypatch, missing, value):
    for name, secret in SECRETS.items():
        monkeypatch.setenv(name, secret)
    if value is None:
        monkeypatch.delenv(missing)
    else:
        monkeypatch.setenv(missing, value)

    with pytest.raises(RuntimeError, match=missing) as exc_info:
        server.run_select("SELECT 1")
    assert not any(secret in str(exc_info.value) for secret in SECRETS.values())
    assert fake_pymysql.connect_kwargs == []


@pytest.mark.parametrize("timeout", ["0", "-5"])
def test_non_positive_timeout_is_rejected(server, fake_pymysql, mysql_env, monkeypatch, timeout):
    monkeypatch.setenv("MYSQL_STATEMENT_TIMEOUT_MS", timeout)
    with pytest.raises(RuntimeError, match="MYSQL_STATEMENT_TIMEOUT_MS"):
        server.run_select("SELECT 1")
    assert fake_pymysql.connect_kwargs == []


def test_max_execution_time_failure_is_reported(server, fake_pymysql, mysql_env):
    conn = fake_pymysql.connection = FakeConnection(fail_on="SET SESSION MAX_EXECUTION_TIME")
    with pytest.raises(RuntimeError, match="MAX_EXECUTION_TIME") as exc_info:
        server.run_select("SELECT 1")
    assert isinstance(exc_info.value.__cause__, FakeMySQLError)
    assert conn.closed
    assert "SELECT 1" not in conn.calls


def test_row_values_are_jsonable(server, fake_pymysql, mysql_env):
    fake_pymysql.connection = FakeConnection(
        rows=[(decimal.Decimal("2.50"), dt.date(2024, 1, 2))], columns=("price", "day")
    )
    result = server.run_select("SELECT price, day FROM t")
    assert result["columns"] == ["price", "day"]
    assert result["rows"] == [[2.5, "2024-01-02"]]


# --- Schema tools against the fake ---------------------------------------------------------


def test_list_tables(server, fake_pymysql, mysql_env):
    conn = fake_pymysql.connection = FakeConnection(rows=[("shop", "orders"), ("hr", "emp")])
    assert server.list_tables() == {"tables": ["orders", "hr.emp"]}

    [query] = [sql for sql in statements(conn) if "information_schema.tables" in sql]
    for schema in ("mysql", "information_schema", "performance_schema", "sys"):
        assert f"'{schema}'" in query
    assert "table_type IN ('BASE TABLE', 'VIEW')" in query
    assert conn.closed


@pytest.mark.parametrize(
    ("table", "params"), [("orders", ("shop", "orders")), ("hr.emp", ("hr", "emp"))]
)
def test_describe_table(server, fake_pymysql, mysql_env, table, params):
    conn = fake_pymysql.connection = FakeConnection(
        rows=[("id", "int", "NO"), ("note", "text", "YES")]
    )
    assert server.describe_table(table) == {
        "table": table,
        "columns": [
            {"name": "id", "type": "int", "nullable": False},
            {"name": "note", "type": "text", "nullable": True},
        ],
    }

    [(sql, used)] = [(s, p) for s, p in conn.params if "information_schema.columns" in s]
    assert used == params
    assert not any(part in sql.lower() for part in params)  # passed as parameters only
    assert conn.closed


def test_describe_unknown_table(server, fake_pymysql, mysql_env):
    conn = fake_pymysql.connection = FakeConnection(rows=[])
    with pytest.raises(ValueError, match="Unknown table"):
        server.describe_table("missing")
    assert conn.closed


# --- Integration against a real MySQL (opt-in) ---------------------------------------------

_REQUIRED = ("MYSQL_TEST_HOST", "MYSQL_TEST_USER", "MYSQL_TEST_PASSWORD", "MYSQL_TEST_DATABASE")
needs_mysql = pytest.mark.skipif(
    not all(name in os.environ for name in _REQUIRED),
    reason=f"set {', '.join(_REQUIRED)} to run the MySQL integration tests",
)


@pytest.fixture
def mysql_spec():
    pytest.importorskip("pymysql")
    return MCPServerSpec(
        id="test-mysql",
        name="Test MySQL",
        dialect="mysql",
        command=sys.executable,
        args=[str(SERVER_PATH)],
        env={
            "MYSQL_HOST": os.environ["MYSQL_TEST_HOST"],
            "MYSQL_PORT": os.environ.get("MYSQL_TEST_PORT", "3306"),
            "MYSQL_USER": os.environ["MYSQL_TEST_USER"],
            "MYSQL_PASSWORD": os.environ["MYSQL_TEST_PASSWORD"],
            "MYSQL_DATABASE": os.environ["MYSQL_TEST_DATABASE"],
        },
    )


@needs_mysql
async def test_mysql_duplicate_column_names(mysql_spec):
    result = await MCPClient().call_tool(mysql_spec, "run_select", {"sql": "SELECT 1 AS a, 2 AS a"})
    assert result["columns"] == ["a", "a"] and len(result["rows"]) == 1


@needs_mysql
async def test_mysql_truncation(mysql_spec):
    sql = (
        "WITH RECURSIVE n (i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < 500) "
        "SELECT i FROM n"
    )
    result = await MCPClient().call_tool(mysql_spec, "run_select", {"sql": sql, "max_rows": 5})
    assert len(result["rows"]) == 5 and result["truncated"] is True


@needs_mysql
async def test_mysql_session_is_configured(mysql_spec):
    sql = "SELECT @@transaction_read_only AS ro, @@max_execution_time AS t, @@sql_select_limit AS l"
    result = await MCPClient().call_tool(mysql_spec, "run_select", {"sql": sql, "max_rows": 7})
    assert result["columns"] == ["ro", "t", "l"]
    assert result["rows"] == [[1, 30000, 8]]


@needs_mysql
async def test_mysql_statement_timeout(mysql_spec):
    # Reads only information_schema, so no tables are required. A plain COUNT(*) over a cross
    # join is not enough: MySQL can answer that without generating the rows.
    sql = (
        "SELECT COUNT(*) FROM information_schema.columns a, information_schema.columns b, "
        "information_schema.columns c "
        "WHERE a.ordinal_position + b.ordinal_position + c.ordinal_position = -1"
    )
    spec = mysql_spec.model_copy(
        update={"env": {**mysql_spec.env, "MYSQL_STATEMENT_TIMEOUT_MS": "1000"}}
    )
    start = time.monotonic()
    with pytest.raises(MCPToolError, match=r"(?i)maximum statement execution time|3024"):
        await MCPClient().call_tool(spec, "run_select", {"sql": sql})
    assert time.monotonic() - start < 10


@needs_mysql
async def test_mysql_rejects_writes_by_prefix(mysql_spec):
    with pytest.raises(MCPToolError, match="Only SELECT"):
        await MCPClient().call_tool(mysql_spec, "run_select", {"sql": "DELETE FROM x"})


@needs_mysql
async def test_mysql_rejects_write_behind_select_prefix(mysql_spec):
    # The exact MySQL error depends on the test user's privileges (missing DELETE grant vs.
    # read-only transaction). The read-only enforcement itself is verified by
    # test_mysql_session_is_configured and by a manual check with a privileged user.
    table = os.environ.get("MYSQL_TEST_TABLE")
    if not table:
        pytest.skip("set MYSQL_TEST_TABLE to run this test")
    sql = f"WITH x AS (SELECT 1) DELETE FROM {table} WHERE 1 = 0"
    with pytest.raises(MCPToolError):
        await MCPClient().call_tool(mysql_spec, "run_select", {"sql": sql})


@needs_mysql
async def test_mysql_list_and_describe(mysql_spec):
    client = MCPClient()
    tables = (await client.call_tool(mysql_spec, "list_tables"))["tables"]
    assert isinstance(tables, list)

    if table := os.environ.get("MYSQL_TEST_TABLE"):
        assert table in tables
        info = await client.call_tool(mysql_spec, "describe_table", {"table": table})
        assert info["columns"]
        assert all({"name", "type", "nullable"} <= set(c) for c in info["columns"])

    with pytest.raises(MCPToolError):
        await client.call_tool(mysql_spec, "describe_table", {"table": "dlc_no_such_table_x"})
