import asyncio

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..mcp_client import MCPToolError
from ..registry import UnknownDataSource

router = APIRouter(prefix="/datasources", tags=["datasources"])


class DataSourceInfo(BaseModel):
    id: str
    name: str
    description: str
    dialect: str


class TableInfo(BaseModel):
    name: str
    columns: list[dict]


@router.get("", response_model=list[DataSourceInfo])
def list_datasources(request: Request) -> list[DataSourceInfo]:
    # Deliberately omits command/args/env: those may reference secrets.
    return [
        DataSourceInfo(id=s.id, name=s.name, description=s.description, dialect=s.dialect)
        for s in request.app.state.registry.list()
    ]


@router.get("/{datasource_id}/schema", response_model=list[TableInfo])
async def schema(datasource_id: str, request: Request) -> list[TableInfo]:
    gateway = request.app.state.gateway
    try:
        tables = await gateway.list_tables(datasource_id)
        described = await asyncio.gather(
            *(gateway.describe_table(datasource_id, t) for t in tables)
        )
    except UnknownDataSource:
        raise HTTPException(404, f"Unknown data source {datasource_id!r}") from None
    except MCPToolError as exc:
        raise HTTPException(502, str(exc)) from exc
    return [TableInfo(name=t, columns=d["columns"]) for t, d in zip(tables, described, strict=True)]
