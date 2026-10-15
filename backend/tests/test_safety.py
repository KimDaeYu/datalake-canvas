import pytest

from datalake_canvas.safety import SafetyGuard, SafetyViolation, check_sql

## Allowed List
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
        "SELECT $$DROP TABLE x$$",
        "VALUES (1), (2)",
        "$SELECT$",
        "SELECT 'it''s; DROP TABLE t'",
        'SELECT "a"";DROP TABLE t;--" FROM t',
        "SELECT $tag$it's; DROP TABLE t$tag$",
        "SELECT $a$ $b$ ; DROP $a$",  # $b$ is just content inside $a$
        "SELECT 1 -- trailing comment, no newline",
        "SELECT 1; -- trailing comment",
        "SELECT 1; /* trailing */",
        "SELECT\t1\r\n",
    ],
)
def test_allows_read_only_queries(sql):
    check_sql(sql)

## Blocked List
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
        "$",
        "",
        "   ;  ",
        "EXPLAIN ANALYZE DELETE FROM t", # ANALYZE actually executes it lol
        "COPY t TO '/tmp/out.csv'",
        "COPY t TO PROGRAM 'rm -rf /'",
        "GRANT ALL ON t TO public",
        "MERGE INTO t USING s ON t.id = s.id WHEN MATCHED THEN DELETE",
        "CALL some_proc()",
        "SET search_path = evil",
        "LOAD 'some_extension'",
        "INSTALL httpfs",
        "WITH x AS (SELECT 1) INSERT INTO t SELECT * FROM x",
        "SELECT * /**/INTO t FROM x",
        "DROP/**/TABLE t",
        "dRoP TABLE t",
        "SELECT * FROM t FOR UPDATE",     
        "SELECT E'\\'' ; DROP TABLE t; --'", # E-string backslash escape must not hide the second statement from the guard
        "$$DROP TABLE", #Dollar String that never closes 
        "SELECT 1 /* /* */; DROP TABLE t; /* */ */",
        "SELECT 1 /* a /* b */ c */; DROP TABLE t",
        "SELECT $a$x$a$; DROP TABLE t", # closed quote, then stacked stmt
        "SELECT $a$ x $b$; DROP TABLE t", # mismatched tag = unterminated
        "SELECT $1; DROP TABLE t", # $1 is a param, not a quote
        "SELECT foo$bar$ FROM t; DROP TABLE t; SELECT $bar$", # $ inside identifier (valid in Postgres)
        "DO $$ BEGIN DELETE FROM t; END $$", # dangerous body inside a literal
    ],
)
def test_blocks_unsafe_queries(sql):
    with pytest.raises(SafetyViolation):
        check_sql(sql)


def test_write_mode_allows_destructive_but_still_single_statement():
    check_sql("DELETE FROM t WHERE id = 1", allow_write=True)
    check_sql("DROP TABLE t", allow_write=True)
    with pytest.raises(SafetyViolation):
        check_sql("DELETE FROM t; DROP TABLE t", allow_write=True)


def test_guard_defaults_to_read_only_and_reports_reason():
    guard = SafetyGuard()
    assert guard.allow_write is False
    ok = guard.check("SELECT 1")
    assert ok.allowed and ok.reason is None
    bad = guard.check("TRUNCATE t")
    assert not bad.allowed and "TRUNCATE" in bad.reason
    with pytest.raises(SafetyViolation):
        guard.validate("DROP TABLE t")


def test_guard_with_write_enabled():
    assert SafetyGuard(allow_write=True).check("UPDATE t SET a = 1").allowed
