import pytest

from datalake_canvas.agent.base import LLMProvider, PlanRequest, QueryPlan
from datalake_canvas.agent.planner import QueryPlanner
from datalake_canvas.gateway import MCPDataGateway
from datalake_canvas.mcp_client import MCPServerSpec
from datalake_canvas.registry import DataSourceRegistry
from datalake_canvas.safety import SafetyGuard, SafetyViolation, check_sql
from tests.conftest import FakeGateway

# None and an unknown engine read the statement under every dialect's rules.
DIALECTS = [None, "postgresql", "sqlite", "mysql", "some-other-engine"]


# --- behaviour that does not depend on the dialect -------------------------------------


@pytest.mark.parametrize("dialect", DIALECTS)
@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM orders",
        "  select id from t where name = 'x';  ",
        "WITH a AS (SELECT 1) SELECT * FROM a",
        "SELECT 'DROP TABLE users' AS note",  # keyword inside a literal is fine
        'SELECT "delete" FROM t',  # quoted identifier
        "SELECT 1 -- DROP TABLE users",  # keyword inside a comment
        "SELECT /* DELETE FROM t */ 1",
        "SELECT update_time, created_at FROM t",  # keywords only as identifier prefixes
        "SELECT replace(name, 'a', 'b') FROM t",
        "VALUES (1), (2)",
        "SELECT `a b` FROM t",
    ],
)
def test_allows_read_only_queries(sql, dialect):
    check_sql(sql, dialect=dialect)


@pytest.mark.parametrize("dialect", DIALECTS)
@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE users",
        "delete from users",
        "UPDATE users SET name = 'x'",
        "ALTER TABLE users ADD COLUMN x int",
        "TRUNCATE users",
        "INSERT INTO users VALUES (1)",
        "CREATE TABLE t (id int)",
        "SELECT * FROM t; DROP TABLE t",  # stacked statements
        "SELECT 1; SELECT 2",
        "WITH d AS (DELETE FROM t RETURNING *) SELECT * FROM d",  # data-modifying CTE
        "SELECT * INTO new_table FROM t",
        "PRAGMA writable_schema = 1",
        "ATTACH DATABASE 'x.db' AS x",
        "/* hi */ DELETE FROM t",
        "SELECT 1 /* unterminated",
        "SELECT 'unterminated",
        "",
        "   ;  ",
    ],
)
def test_blocks_unsafe_queries(sql, dialect):
    with pytest.raises(SafetyViolation):
        check_sql(sql, dialect=dialect)


def test_write_mode_allows_destructive_but_still_single_statement():
    check_sql("DELETE FROM t WHERE id = 1", allow_write=True)
    check_sql("DROP TABLE t", allow_write=True)
    with pytest.raises(SafetyViolation):
        check_sql("DELETE FROM t; DROP TABLE t", allow_write=True)
    # the dialect-specific lexing still applies in write mode: a hidden second statement
    with pytest.raises(SafetyViolation):
        check_sql("DELETE FROM t /*! ; DROP TABLE t */", allow_write=True, dialect="mysql")


# --- PostgreSQL ------------------------------------------------------------------------


def test_dollar_quoting_hides_keywords_only_for_postgresql():
    sql = "SELECT $$DROP TABLE x$$"
    check_sql(sql, dialect="postgresql")
    for dialect in (None, "sqlite", "mysql", "some-other-engine"):
        with pytest.raises(SafetyViolation, match="DROP"):
            check_sql(sql, dialect=dialect)


@pytest.mark.parametrize("dialect", [None, "postgresql"])
def test_e_string_backslash_escape_cannot_hide_a_second_statement(dialect):
    with pytest.raises(SafetyViolation):
        check_sql("SELECT E'\\'' ; DROP TABLE t; --'", dialect=dialect)


# --- MySQL: it lexes differently from PostgreSQL ---------------------------------------

MYSQL_BYPASSES = [
    # a backslash-escaped quote keeps the string open, then "-- " starts a comment
    r"SELECT 'a\'' INTO OUTFILE '/tmp/x' -- '",
    # "--1" is arithmetic in MySQL, not a comment
    "SELECT 1 --1 INTO OUTFILE '/tmp/x'",
    # the content of /*! ... */ is executed by the server
    "SELECT 1 /*!50000 INTO OUTFILE '/tmp/x' */",
    "SELECT 1 /*! INTO OUTFILE '/tmp/x' */",
    "SELECT 1 /*M!100100 INTO OUTFILE '/tmp/x' */",
    # "#" starts a comment in MySQL: the quote inside it is not a string start, so the
    # following line is code (a guard without "#" comments would see one long string)
    "SELECT 1 # '\n; DROP TABLE t; -- '",
    "SELECT 1 # c\nINTO OUTFILE '/tmp/x'",
    # ANSI_QUOTES / NO_BACKSLASH_ESCAPES: where a quoted token ends depends on sql_mode
    r"""SELECT "a\" INTO OUTFILE '/tmp/x' -- " """,
    r"SELECT 'a\' INTO OUTFILE '/tmp/x' -- '",
    "SELECT 1 /*!50000 ; DROP TABLE t */",  # a second statement inside an executable comment
]


@pytest.mark.parametrize("dialect", ["mysql", "MySQL", "mariadb", None, "some-other-engine"])
@pytest.mark.parametrize("sql", MYSQL_BYPASSES)
def test_mysql_lexing_differences_cannot_hide_statements(sql, dialect):
    with pytest.raises(SafetyViolation):
        check_sql(sql, dialect=dialect)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 'it\\'s' AS s",  # backslash-escaped quote, valid in the default mode
        "SELECT 'it''s' AS s",
        "SELECT 1 # just a comment",
        "SELECT 1 # it's a comment with a quote\n",
        "SELECT 1 -- just a comment",
        "SELECT 1 --1",  # arithmetic, no INTO
        "SELECT 'a into b' AS s",
        "SELECT `into` FROM t",
    ],
)
def test_mysql_allows_ordinary_queries(sql):
    check_sql(sql, dialect="mysql")


@pytest.mark.parametrize("dialect", ["mysql", None])
def test_mysql_optimizer_hints_are_rejected(dialect):
    with pytest.raises(SafetyViolation, match="hints"):
        check_sql("SELECT /*+ NO_ICP(t) */ 1 FROM t", dialect=dialect)


@pytest.mark.parametrize("dialect", ["postgresql", "sqlite"])
def test_hints_are_ordinary_comments_for_other_engines(dialect):
    check_sql("SELECT /*+ NO_ICP(t) */ 1 FROM t", dialect=dialect)


# --- SQLite: [bracket] identifiers -----------------------------------------------------


@pytest.mark.parametrize("dialect", ["sqlite", None])
def test_sqlite_bracket_identifier_cannot_hide_a_second_statement(dialect):
    # SQLite reads [a'] as one identifier; PostgreSQL rules would see a string start at the quote
    with pytest.raises(SafetyViolation):
        check_sql("SELECT [a'] FROM t; DROP TABLE t; --'", dialect=dialect)


def test_sqlite_allows_a_bracketed_keyword_but_unknown_dialects_do_not():
    sql = "SELECT [delete] FROM t"
    check_sql(sql, dialect="sqlite")
    with pytest.raises(SafetyViolation, match="DELETE"):
        check_sql(sql, dialect=None)  # conservative: one of the readings sees a DELETE keyword


# --- dialect names ---------------------------------------------------------------------


@pytest.mark.parametrize("dialect", ["postgres", "PG", " PostgreSQL "])
def test_postgresql_aliases(dialect):
    check_sql("SELECT $$DROP TABLE x$$", dialect=dialect)


@pytest.mark.parametrize("dialect", ["sqlite3", "SQLite"])
def test_sqlite_aliases(dialect):
    check_sql("SELECT [delete] FROM t", dialect=dialect)


def test_the_default_spec_dialect_is_treated_as_unknown():
    # MCPServerSpec.dialect defaults to "sql": it must get the conservative treatment
    assert MCPServerSpec(id="x", name="x", command="x").dialect == "sql"
    with pytest.raises(SafetyViolation):
        check_sql("SELECT 1 /*! INTO OUTFILE '/tmp/x' */", dialect="sql")


def test_a_quote_that_only_one_reading_can_close_is_not_an_error():
    # unterminated without backslash escapes, a valid string in MySQL's default mode
    check_sql(r"SELECT 'a\'b' AS s", dialect="mysql")
    check_sql(r"SELECT 'a\'b' AS s", dialect=None)


# --- the guard class and its call sites ------------------------------------------------


def test_guard_defaults_to_read_only_and_reports_reason():
    guard = SafetyGuard()
    assert guard.allow_write is False
    ok = guard.check("SELECT 1")
    assert ok.allowed and ok.reason is None
    bad = guard.check("TRUNCATE t")
    assert not bad.allowed and "TRUNCATE" in bad.reason
    with pytest.raises(SafetyViolation):
        guard.validate("DROP TABLE t")


def test_guard_passes_the_dialect_through():
    guard = SafetyGuard()
    assert guard.check("SELECT [delete] FROM t", dialect="sqlite").allowed
    assert not guard.check("SELECT [delete] FROM t").allowed
    assert not guard.check("SELECT 1 /*! INTO OUTFILE '/tmp/x' */", dialect="mysql").allowed


def test_guard_with_write_enabled():
    assert SafetyGuard(allow_write=True).check("UPDATE t SET a = 1").allowed


class _NeverCalledClient:
    async def call_tool(self, spec, tool, arguments=None):  # pragma: no cover
        raise AssertionError("the guard must reject the statement before the server is called")


def _gateway(dialect):
    registry = DataSourceRegistry([MCPServerSpec(id="ds", name="ds", dialect=dialect, command="x")])
    return MCPDataGateway(registry, _NeverCalledClient(), SafetyGuard())


async def test_gateway_reads_the_statement_with_the_data_sources_dialect():
    with pytest.raises(SafetyViolation):
        await _gateway("mysql").run_select("ds", "SELECT 1 /*! INTO OUTFILE '/tmp/x' */")
    # the same bracketed identifier is fine for SQLite and rejected for an unknown dialect
    with pytest.raises(AssertionError, match="before the server"):
        await _gateway("sqlite").run_select("ds", "SELECT [delete] FROM t")  # reached the client
    with pytest.raises(SafetyViolation):
        await _gateway("sql").run_select("ds", "SELECT [delete] FROM t")


class _FixedProvider(LLMProvider):
    name = "fixed"

    def __init__(self, sql):
        self.sql = sql

    async def plan_query(self, request: PlanRequest) -> QueryPlan:
        return QueryPlan(sql=self.sql, explanation="")


async def test_planner_checks_the_plan_with_the_data_sources_dialect():
    sql = "SELECT 1 /*! INTO OUTFILE '/tmp/x' */"
    for dialect, allowed in [("mysql", False), ("postgresql", True)]:
        registry = DataSourceRegistry(
            [MCPServerSpec(id="ds", name="ds", dialect=dialect, command="x")]
        )
        planner = QueryPlanner(
            FakeGateway(datasources=("ds",)), registry, _FixedProvider(sql), SafetyGuard()
        )
        assert (await planner.plan("q", "ds")).safety.allowed is allowed
