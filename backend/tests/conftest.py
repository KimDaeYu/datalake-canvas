import sqlite3
from pathlib import Path
from typing import Any

import pytest

from datalake_canvas.models import TableData

REPO_ROOT = Path(__file__).resolve().parents[2]


class FakeGateway:
    """In-memory DataGateway: maps SQL text to canned tables and records calls."""

    def __init__(self, tables: dict[str, TableData] | None = None, datasources=("demo",)):
        self.tables = tables or {}
        self.datasources = set(datasources)
        self.calls: list[tuple[str, str]] = []

    def has_datasource(self, datasource_id: str) -> bool:
        return datasource_id in self.datasources

    async def run_select(
        self, datasource_id: str, sql: str, max_rows: int | None = None
    ) -> TableData:
        self.calls.append((datasource_id, sql))
        if sql not in self.tables:
            raise RuntimeError(f"no canned result for {sql!r}")
        return self.tables[sql]

    async def list_tables(self, datasource_id: str) -> list[str]:
        return ["orders"]

    async def describe_table(self, datasource_id: str, table: str) -> dict[str, Any]:
        return {"table": table, "columns": [{"name": "id", "type": "INTEGER"}]}


@pytest.fixture
def sales_table() -> TableData:
    return TableData(
        columns=["region", "revenue"],
        rows=[["EU", 120.5], ["NA", 300], ["APAC", 80], ["LATAM", None]],
    )


@pytest.fixture
def demo_db(tmp_path: Path) -> Path:
    """A real SQLite file built from the committed demo.sql."""
    path = tmp_path / "demo.db"
    conn = sqlite3.connect(path)
    conn.executescript((REPO_ROOT / "examples" / "demo-data" / "demo.sql").read_text())
    conn.commit()
    conn.close()
    return path
