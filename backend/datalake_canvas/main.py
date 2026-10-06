"""Application factory. Run with: ``uvicorn datalake_canvas.main:create_app --factory``."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .agent import LLMProvider, create_provider
from .config import Settings, get_settings
from .executor import WorkflowExecutor
from .gateway import DataGateway, MCPDataGateway
from .mcp_client import MCPClient
from .registry import DataSourceRegistry
from .routes import agent, datasources, health, workflows
from .safety import SafetyGuard
from .store import WorkflowStore

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    *,
    gateway: DataGateway | None = None,
    registry: DataSourceRegistry | None = None,
    provider: LLMProvider | None = None,
) -> FastAPI:
    """Build the app. The keyword arguments let tests inject fakes."""
    settings = settings or get_settings()
    guard = SafetyGuard(allow_write=settings.allow_write_queries)
    if guard.allow_write:
        logger.warning("DLC_ALLOW_WRITE_QUERIES is enabled: the SQL safety guard is relaxed")

    if registry is None:
        registry = DataSourceRegistry.from_file(
            settings.resolved_datasources_file,
            variables={
                "DLC_ROOT": str(settings.root),
                "DLC_DATA_DIR": str(settings.resolved_data_dir),
            },
        )
    if gateway is None:
        gateway = MCPDataGateway(
            registry, MCPClient(settings.query_timeout_seconds), guard, settings.max_rows
        )
    if provider is None:
        provider = create_provider(settings)

    app = FastAPI(
        title="DataLake Canvas API",
        version=__version__,
        description="Workflow storage and execution, MCP-backed data access and a query-planning agent.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.settings = settings
    app.state.guard = guard
    app.state.registry = registry
    app.state.gateway = gateway
    app.state.provider = provider
    app.state.store = WorkflowStore(settings.workflows_dir)
    app.state.executor = WorkflowExecutor(gateway, settings.max_rows)

    for module in (health, datasources, workflows, agent):
        app.include_router(module.router)
    return app
