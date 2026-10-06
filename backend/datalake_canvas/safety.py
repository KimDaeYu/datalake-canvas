"""Read-only SQL guard.

This is *defense in depth*, not a SQL parser: it strips comments and string literals,
rejects multi-statement input, requires a read-only leading keyword and blocks
write/DDL keywords anywhere in the statement (which also catches data-modifying CTEs
such as ``WITH x AS (DELETE ...)``). The reference MCP servers additionally open their
connections read-only, so the database itself is the last line of defense.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


class SafetyViolation(Exception):
    """Raised when a query is rejected by the guard."""


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


def _strip_literals(sql: str) -> str:
    """Replace comments, quoted strings and quoted identifiers with neutral tokens."""
    out: list[str] = []
    i, n = 0, len(sql)
    while i < n:
        c = sql[i]
        if sql.startswith("--", i):
            j = sql.find("\n", i)
            i = n if j == -1 else j
            out.append(" ")
        elif sql.startswith("/*", i):
            j = sql.find("*/", i + 2)
            if j == -1:
                raise SafetyViolation("Unterminated block comment")
            i = j + 2
            out.append(" ")
        elif c in "'\"`":
            # PostgreSQL E'...' strings treat backslash as an escape character. Mirror
            # that so an escaped quote cannot hide the rest of the statement from us.
            backslash_escapes = (
                c == "'"
                and i > 0
                and sql[i - 1] in "eE"
                and (i < 2 or not (sql[i - 2].isalnum() or sql[i - 2] == "_"))
            )
            j = i + 1
            while True:
                if j >= n:
                    raise SafetyViolation("Unterminated quoted string or identifier")
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
        elif c == "$" and (m := _DOLLAR_TAG.match(sql, i)):
            tag = m.group(0)
            j = sql.find(tag, m.end())
            if j == -1:
                raise SafetyViolation("Unterminated dollar-quoted string")
            i = j + len(tag)
            out.append(_PLACEHOLDER)
        else:
            out.append(c)
            i += 1
    return "".join(out)


def check_sql(sql: str, *, allow_write: bool = False) -> None:
    """Raise :class:`SafetyViolation` if ``sql`` may not be executed."""
    if not sql or not sql.strip():
        raise SafetyViolation("Query is empty")
    statements = [s for s in _strip_literals(sql).split(";") if s.strip()]
    if not statements:
        raise SafetyViolation("Query is empty")
    if len(statements) > 1:
        raise SafetyViolation("Multiple statements are not allowed")
    if allow_write:
        return
    words = [w.upper() for w in _WORD.findall(statements[0])]
    if words[0] not in READ_ONLY_START:
        raise SafetyViolation(
            f"Only SELECT queries are allowed in read-only mode (statement starts with {words[0]})"
        )
    for word in words:
        if word in BLOCKED_KEYWORDS:
            raise SafetyViolation(f"Keyword {word} is blocked in read-only mode")


@dataclass(frozen=True)
class GuardResult:
    allowed: bool
    reason: str | None = None


class SafetyGuard:
    """Config-bound wrapper around :func:`check_sql`."""

    def __init__(self, allow_write: bool = False) -> None:
        self.allow_write = allow_write

    def validate(self, sql: str) -> None:
        check_sql(sql, allow_write=self.allow_write)

    def check(self, sql: str) -> GuardResult:
        try:
            self.validate(sql)
        except SafetyViolation as exc:
            return GuardResult(False, str(exc))
        return GuardResult(True)
