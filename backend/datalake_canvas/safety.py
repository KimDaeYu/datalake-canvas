"""Read-only SQL guard.

This is *defense in depth*, not a SQL parser: it strips comments and string literals,
rejects multi-statement input, requires a read-only leading keyword and blocks
write/DDL keywords anywhere in the statement (which also catches data-modifying CTEs
such as ``WITH x AS (DELETE ...)``). The reference MCP servers additionally open their
connections read-only, so the database itself is the last line of defense.

The guard has to read the text the way the *database* reads it, otherwise a statement can
look harmless to the guard and mean something else to the engine (a quote that is an escape in
one engine and not in another decides what counts as "inside a string"). Each dialect therefore
has its own lexing rules (``_Rules``). A statement is accepted only if **every** reading allowed
for the dialect accepts it:

* ``postgresql``: ``E'...'`` backslash escapes, dollar quoting
* ``sqlite``: ``[...]`` quoted identifiers
* ``mysql``: backslash escapes in strings, ``#`` comments, ``--`` only before whitespace,
  executable ``/*! ... */`` comments and optimizer hints ``/*+ ... */`` are rejected. The server's
  ``sql_mode`` may or may not have ``NO_BACKSLASH_ESCAPES``, so MySQL is read both ways.
* anything else (unknown dialect, or none given): read with **all** of the rules above.
  This rejects more than necessary but never less.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace


class SafetyViolation(Exception):
    """Raised when a query is rejected by the guard."""


class _Unterminated(SafetyViolation):
    """A quote or comment never closes under one particular reading."""


READ_ONLY_START = frozenset({"SELECT", "WITH", "VALUES"})

# Blocked anywhere in a read-only statement. The first five are the destructive
# statements called out in the project docs; the rest are other ways to mutate state.
BLOCKED_KEYWORDS = frozenset(
    {
        "DROP", "DELETE", "UPDATE", "ALTER", "TRUNCATE",
        "INSERT", "CREATE", "MERGE", "GRANT", "REVOKE", "COPY", "CALL", "EXEC",
        "EXECUTE", "ATTACH", "DETACH", "PRAGMA", "VACUUM", "REINDEX", "INTO",
    }
)  # fmt: skip

_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_$]*")
_DOLLAR_TAG = re.compile(r"\$(?:[A-Za-z_][A-Za-z0-9_]*)?\$")
_PLACEHOLDER = " _lit_ "


@dataclass(frozen=True)
class _Rules:
    """How one engine lexes comments and quoted text."""

    name: str
    backslash_escapes: bool = False  # backslash escapes inside '...' and "..."
    e_strings: bool = False  # backslash escapes only inside E'...' (PostgreSQL)
    dollar_quotes: bool = False  # $tag$ ... $tag$
    bracket_identifiers: bool = False  # [ident] (SQLite, SQL Server)
    hash_comments: bool = False  # '#' starts a line comment (MySQL)
    dashdash_needs_space: bool = False  # '--' is a comment only before whitespace (MySQL)
    reject_executable_comments: bool = False  # /*! ... */ and /*M! ... */ (MySQL, MariaDB)
    reject_hints: bool = False  # /*+ ... */ optimizer hints (MySQL)


_POSTGRESQL = _Rules("postgresql", e_strings=True, dollar_quotes=True)
_SQLITE = _Rules("sqlite", bracket_identifiers=True)
_MYSQL = _Rules(
    "mysql",
    hash_comments=True,
    dashdash_needs_space=True,
    reject_executable_comments=True,
    reject_hints=True,
)
_MYSQL_ESCAPES = replace(_MYSQL, backslash_escapes=True)

_BY_DIALECT: dict[str, tuple[_Rules, ...]] = {
    "postgresql": (_POSTGRESQL,),
    "sqlite": (_SQLITE,),
    "mysql": (_MYSQL_ESCAPES, _MYSQL),  # sql_mode may or may not have NO_BACKSLASH_ESCAPES
}
_ALIASES = {
    "postgres": "postgresql",
    "pg": "postgresql",
    "sqlite3": "sqlite",
    "mariadb": "mysql",
}
_ALL_READINGS: tuple[_Rules, ...] = (_POSTGRESQL, _SQLITE, _MYSQL_ESCAPES, _MYSQL)


def _normalize(dialect: str | None) -> str:
    key = (dialect or "").strip().lower()
    return _ALIASES.get(key, key)


def _readings(dialect: str | None) -> tuple[_Rules, ...]:
    """The lexing rules a statement must satisfy for this dialect (all of them if unknown)."""
    return _BY_DIALECT.get(_normalize(dialect), _ALL_READINGS)


def _unmodelled_hint(dialect: str | None) -> str:
    """How to relax the check, appended to rejections made under the strictest (all) readings."""
    if _normalize(dialect) in _BY_DIALECT:
        return ""
    which = (
        f"data source dialect {dialect!r} is not modelled" if dialect else "no dialect was given"
    )
    return (
        f" ({which}, so the strictest reading is applied; set the data source's `dialect` to a"
        " similar engine (postgresql, sqlite or mysql) to relax this check)"
    )


def _strip_literals(sql: str, rules: _Rules) -> str:
    """Replace comments, quoted strings and quoted identifiers with neutral tokens."""
    out: list[str] = []
    i, n = 0, len(sql)
    while i < n:
        c = sql[i]
        if sql.startswith("--", i):
            # MySQL: "--" starts a comment only when followed by whitespace/control char or EOF.
            if rules.dashdash_needs_space and not (i + 2 == n or sql[i + 2] <= " "):
                out.append(c)
                i += 1
                continue
            j = sql.find("\n", i)
            i = n if j == -1 else j
            out.append(" ")
        elif c == "#" and rules.hash_comments:
            j = sql.find("\n", i)
            i = n if j == -1 else j
            out.append(" ")
        elif sql.startswith("/*", i):
            if rules.reject_executable_comments and sql.startswith(("/*!", "/*M!"), i):
                raise SafetyViolation("Executable comments /*! ... */ are not allowed")
            if rules.reject_hints and sql.startswith("/*+", i):
                raise SafetyViolation("Optimizer hints /*+ ... */ are not allowed")
            j = sql.find("*/", i + 2)
            if j == -1:
                raise _Unterminated("Unterminated block comment")
            i = j + 2
            out.append(" ")
        elif c in "'\"`":
            # Where a string ends depends on whether a backslash escapes the next character.
            backslash_escapes = c != "`" and (
                rules.backslash_escapes
                or (
                    rules.e_strings
                    and c == "'"
                    and i > 0
                    and sql[i - 1] in "eE"
                    and (i < 2 or not (sql[i - 2].isalnum() or sql[i - 2] == "_"))
                )
            )
            j = i + 1
            while True:
                if j >= n:
                    raise _Unterminated("Unterminated quoted string or identifier")
                if backslash_escapes and sql[j] == "\\":
                    j += 2
                    continue
                if sql[j] == c:
                    if j + 1 < n and sql[j + 1] == c:  # doubled quote = escaped quote
                        j += 2
                        continue
                    break
                j += 1
            i = j + 1
            out.append(_PLACEHOLDER)
        elif c == "[" and rules.bracket_identifiers:
            j = sql.find("]", i + 1)
            if j == -1:
                raise _Unterminated("Unterminated bracket-quoted identifier")
            i = j + 1
            out.append(_PLACEHOLDER)
        elif c == "$" and rules.dollar_quotes and (m := _DOLLAR_TAG.match(sql, i)):
            tag = m.group(0)
            j = sql.find(tag, m.end())
            if j == -1:
                raise _Unterminated("Unterminated dollar-quoted string")
            i = j + len(tag)
            out.append(_PLACEHOLDER)
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _check_one_reading(sql: str, rules: _Rules, allow_write: bool) -> None:
    statements = [s for s in _strip_literals(sql, rules).split(";") if s.strip()]
    if not statements:
        raise SafetyViolation("Query is empty")
    if len(statements) > 1:
        raise SafetyViolation("Multiple statements are not allowed")
    if allow_write:
        return
    words = [w.upper() for w in _WORD.findall(statements[0])]
    if not words or words[0] not in READ_ONLY_START:
        first = words[0] if words else "?"
        raise SafetyViolation(
            f"Only SELECT queries are allowed in read-only mode (statement starts with {first})"
        )
    for word in words:
        if word in BLOCKED_KEYWORDS:
            raise SafetyViolation(f"Keyword {word} is blocked in read-only mode")


def check_sql(sql: str, *, allow_write: bool = False, dialect: str | None = None) -> None:
    """Raise :class:`SafetyViolation` if ``sql`` may not be executed.

    ``dialect`` selects the lexing rules (see the module docstring); ``None`` or an unknown
    value applies all of them, which is the safe default.
    """
    if not sql or not sql.strip():
        raise SafetyViolation("Query is empty")
    readings = _readings(dialect)
    violation: SafetyViolation | None = None
    unterminated: list[SafetyViolation] = []
    for rules in readings:
        try:
            _check_one_reading(sql, rules, allow_write)
        except _Unterminated as exc:
            unterminated.append(exc)
        except SafetyViolation as exc:
            violation = violation or exc
    # Any reading that sees a problem rejects the statement. A reading in which a quote never
    # closes is not how the engine parses the text (it would be a syntax error there), so it only
    # counts when no reading could make sense of the statement at all.
    rejection = violation or (unterminated[0] if len(unterminated) == len(readings) else None)
    if rejection is not None:
        raise type(rejection)(f"{rejection}{_unmodelled_hint(dialect)}") from None


@dataclass(frozen=True)
class GuardResult:
    allowed: bool
    reason: str | None = None


class SafetyGuard:
    """Config-bound wrapper around :func:`check_sql`."""

    def __init__(self, allow_write: bool = False) -> None:
        self.allow_write = allow_write

    def validate(self, sql: str, dialect: str | None = None) -> None:
        check_sql(sql, allow_write=self.allow_write, dialect=dialect)

    def check(self, sql: str, dialect: str | None = None) -> GuardResult:
        try:
            self.validate(sql, dialect)
        except SafetyViolation as exc:
            return GuardResult(False, str(exc))
        return GuardResult(True)
