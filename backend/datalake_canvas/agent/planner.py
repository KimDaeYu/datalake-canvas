"""Natural language -> validated query plan. The plan is returned, not executed."""

from __future__ import annotations

import asyncio

from pydantic import BaseModel

from ..gateway import DataGateway
from ..registry import DataSourceRegistry
from ..safety import GuardResult, SafetyGuard
from .base import LLMProvider, PlanRequest, QueryPlan

MAX_SCHEMA_TABLES = 25  # keep the prompt bounded for very large databases


class PlanResponse(BaseModel):
    datasource_id: str
    plan: QueryPlan
    safety: GuardResult


class QueryPlanner:
    def __init__(
        self,
        gateway: DataGateway,
        registry: DataSourceRegistry,
        provider: LLMProvider,
        guard: SafetyGuard,
    ) -> None:
        self.gateway = gateway
        self.registry = registry
        self.provider = provider
        self.guard = guard

    async def schema_text(self, datasource_id: str) -> str:
        tables = (await self.gateway.list_tables(datasource_id))[:MAX_SCHEMA_TABLES]
        described = await asyncio.gather(
            *(self.gateway.describe_table(datasource_id, t) for t in tables)
        )
        lines = []
        for table, info in zip(tables, described, strict=True):
            cols = ", ".join(f"{c['name']} {c.get('type', '')}".strip() for c in info["columns"])
            lines.append(f"{table}({cols})")
        return "\n".join(lines) or "(no tables found)"

    async def plan(self, question: str, datasource_id: str) -> PlanResponse:
        spec = self.registry.get(datasource_id)
        request = PlanRequest(
            question=question,
            dialect=spec.dialect,
            schema_text=await self.schema_text(datasource_id),
        )
        plan = await self.provider.plan_query(request)
        # Never trust model output: report whether the guard would let it run.
        return PlanResponse(
            datasource_id=datasource_id,
            plan=plan,
            safety=self.guard.check(plan.sql, dialect=spec.dialect),
        )
