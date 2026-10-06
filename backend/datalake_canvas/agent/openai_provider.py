"""OpenAI provider built on the OpenAI Agents SDK (``openai-agents``)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from .base import (
    SYSTEM_INSTRUCTIONS,
    ChartSuggestion,
    LLMProvider,
    PlanRequest,
    QueryPlan,
    render_prompt,
)


class _PlanOutput(BaseModel):
    """Structured output requested from the model.

    Strict JSON schemas dislike optional fields, so "no chart" is encoded as
    ``chart_type == "none"`` and converted to ``None`` below.
    """

    sql: str
    explanation: str
    chart_type: Literal["bar", "line", "none"]
    x_column: str
    y_column: str


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    async def plan_query(self, request: PlanRequest) -> QueryPlan:
        # Imported lazily so the rest of the backend works without the SDK configured.
        from agents import Agent, Runner, set_default_openai_key

        set_default_openai_key(self.api_key)
        agent = Agent(
            name="DataLake Canvas SQL planner",
            instructions=SYSTEM_INSTRUCTIONS,
            model=self.model,
            output_type=_PlanOutput,
        )
        result = await Runner.run(agent, render_prompt(request))
        out: _PlanOutput = result.final_output
        chart = (
            None
            if out.chart_type == "none"
            else ChartSuggestion(chart_type=out.chart_type, x=out.x_column, y=out.y_column)
        )
        return QueryPlan(sql=out.sql.strip(), explanation=out.explanation, chart=chart)
