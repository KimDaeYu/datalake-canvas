import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..agent.planner import PlanResponse, QueryPlanner
from ..mcp_client import MCPToolError
from ..registry import UnknownDataSource

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agent", tags=["agent"])


class AgentQueryRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    datasource_id: str = Field(min_length=1)


@router.post("/query", response_model=PlanResponse)
async def agent_query(body: AgentQueryRequest, request: Request) -> PlanResponse:
    """Natural language -> query plan. The plan is validated but never executed here."""
    state = request.app.state
    if state.provider is None:
        raise HTTPException(
            503,
            "No LLM provider configured. Set OPENAI_API_KEY (see .env.example) and restart the backend.",
        )
    planner = QueryPlanner(state.gateway, state.registry, state.provider, state.guard)
    try:
        return await planner.plan(body.prompt, body.datasource_id)
    except UnknownDataSource:
        raise HTTPException(404, f"Unknown data source {body.datasource_id!r}") from None
    except MCPToolError as exc:
        raise HTTPException(502, str(exc)) from exc
    except Exception as exc:  # provider/network failures
        logger.exception("agent query failed")
        raise HTTPException(502, f"LLM provider error: {exc}") from exc
