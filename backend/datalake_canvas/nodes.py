"""Per-node configuration schemas and the pure (non-I/O) node logic.

Node configuration lives in ``WorkflowNode.data`` with snake_case keys, e.g.::

    {"type": "transform", "data": {"operation": "sort", "column": "revenue", "descending": true}}
"""

from __future__ import annotations

from typing import Any, Literal, TypeVar

from pydantic import BaseModel, Field, ValidationError, field_validator

from .models import ChartSpec, TableData


class NodeError(Exception):
    """A node could not run; the message is shown to the user on the canvas."""


class DataSourceConfig(BaseModel):
    datasource_id: str = Field(min_length=1)


class QueryConfig(BaseModel):
    sql: str = Field(min_length=1)
    # Optional override; normally the data source comes from the connected DataSource node.
    datasource_id: str | None = None


class TransformConfig(BaseModel):
    operation: Literal["limit", "select", "sort", "filter", "aggregate"]
    n: int | None = Field(default=None, ge=0)  # limit
    columns: list[str] | None = None  # select
    column: str | None = None  # sort / filter / aggregate value
    group_by: str | None = None  # aggregate
    aggregate_op: Literal["sum", "avg", "count", "min", "max"] | None = None
    descending: bool = False  # sort
    op: Literal["==", "!=", ">", ">=", "<", "<=", "contains"] = "=="  # filter
    value: Any = None  # filter

    @field_validator("columns", mode="before")
    @classmethod
    def _split_columns(cls, v: Any) -> Any:
        # The side panel edits columns as a comma-separated string.
        if isinstance(v, str):
            return [c.strip() for c in v.split(",") if c.strip()]
        return v

    @field_validator("n", mode="before")
    @classmethod
    def _blank_n(cls, v: Any) -> Any:
        return None if v == "" else v


class ChartConfig(BaseModel):
    chart_type: Literal["bar", "line"] = "bar"
    x: str = Field(min_length=1)
    y: str = Field(min_length=1)


T = TypeVar("T", bound=BaseModel)


def parse_config(model: type[T], data: dict[str, Any]) -> T:
    """Validate node config, turning pydantic errors into one readable message."""
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in e['loc']) or 'config'}: {e['msg']}" for e in exc.errors()
        )
        raise NodeError(f"Invalid node configuration ({problems})") from exc


def _column_index(table: TableData, column: str | None) -> int:
    if not column:
        raise NodeError("A column name is required")
    try:
        return table.columns.index(column)
    except ValueError:
        raise NodeError(
            f"Unknown column {column!r}; available: {', '.join(table.columns)}"
        ) from None


def _to_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _compare(cell: Any, op: str, value: Any) -> bool:
    if cell is None:
        return op == "!="
    if op == "contains":
        return str(value).lower() in str(cell).lower()
    a, b = _to_number(cell), _to_number(value)
    left, right = (a, b) if a is not None and b is not None else (str(cell), str(value))
    return {
        "==": left == right,
        "!=": left != right,
        ">": left > right,
        ">=": left >= right,
        "<": left < right,
        "<=": left <= right,
    }[op]


def _sorted_rows(rows: list[list[Any]], idx: int, descending: bool) -> list[list[Any]]:
    present = [r for r in rows if r[idx] is not None]
    missing = [r for r in rows if r[idx] is None]  # NULLs always sort last
    try:
        present.sort(key=lambda r: r[idx], reverse=descending)
    except TypeError:  # mixed types in one column: fall back to string order
        present.sort(key=lambda r: str(r[idx]), reverse=descending)
    return present + missing


def _aggregate(table: TableData, cfg: TransformConfig) -> tuple[list[list[Any]], list[str]]:
    try:
        group_idx = _column_index(table, cfg.group_by)
    except NodeError:
        raise NodeError("aggregate requires 'group_by'") from None
    value_idx = _column_index(table, cfg.column)
    groups: dict[Any, list[Any]] = {}
    try:
        for row in table.rows:
            groups.setdefault(row[group_idx], []).append(row[value_idx])
    except TypeError as exc:
        raise NodeError("The group-by column must contain hashable values") from exc

    aggregated_rows = []
    for group, values in groups.items():
        present = [value for value in values if value is not None]
        if cfg.aggregate_op == "count":
            result = len(present)
        elif not present:
            result = None
        elif cfg.aggregate_op in ("sum", "avg"):
            numbers = [_to_number(value) for value in present]
            if any(number is None for number in numbers):
                raise NodeError(
                    f"{cfg.aggregate_op} requires numeric values in column {cfg.column!r}"
                )
            total = sum(number for number in numbers if number is not None)
            result = total if cfg.aggregate_op == "sum" else total / len(numbers)
        else:
            try:
                result = min(present) if cfg.aggregate_op == "min" else max(present)
            except TypeError as exc:
                raise NodeError(
                    f"{cfg.aggregate_op} values in column {cfg.column!r} are not comparable"
                ) from exc
        aggregated_rows.append([group, result])

    columns = [table.columns[group_idx], f"{cfg.aggregate_op}_{table.columns[value_idx]}"]
    return aggregated_rows, columns


def apply_transform(table: TableData, cfg: TransformConfig) -> TableData:
    rows, columns = table.rows, table.columns
    if cfg.operation == "limit":
        if cfg.n is None:
            raise NodeError("limit requires 'n'")
        rows = rows[: cfg.n]
    elif cfg.operation == "select":
        if not cfg.columns:
            raise NodeError("select requires at least one column")
        idxs = [_column_index(table, c) for c in cfg.columns]
        columns = [table.columns[i] for i in idxs]
        rows = [[r[i] for i in idxs] for r in rows]
    elif cfg.operation == "sort":
        rows = _sorted_rows(rows, _column_index(table, cfg.column), cfg.descending)
    elif cfg.operation == "filter":
        idx = _column_index(table, cfg.column)
        rows = [r for r in rows if _compare(r[idx], cfg.op, cfg.value)]
    elif cfg.operation == "aggregate":
        if not cfg.aggregate_op:
            raise NodeError("aggregate requires 'aggregate_op'")
        rows, columns = _aggregate(table, cfg)
    return TableData(columns=columns, rows=rows, truncated=table.truncated)


def build_chart(table: TableData, cfg: ChartConfig) -> ChartSpec:
    _column_index(table, cfg.x)
    _column_index(table, cfg.y)
    return ChartSpec(chart_type=cfg.chart_type, x=cfg.x, y=cfg.y, data=table)
