from fastapi import APIRouter, Request

from .. import __version__

router = APIRouter(tags=["health"])


@router.get("/health")
def health(request: Request) -> dict:
    state = request.app.state
    return {
        "status": "ok",
        "version": __version__,
        "read_only": not state.settings.allow_write_queries,
        "llm_configured": state.provider is not None,
    }
