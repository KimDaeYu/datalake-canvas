from fastapi import APIRouter, HTTPException, Request, Response, status

from ..executor import WorkflowError
from ..models import RunResult, Workflow, WorkflowIn, WorkflowSummary
from ..store import WorkflowNotFound

router = APIRouter(prefix="/workflows", tags=["workflows"])


def _not_found(workflow_id: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"Workflow {workflow_id!r} not found")


# CRUD handlers are plain ``def`` so FastAPI runs the blocking file I/O in its threadpool.


@router.get("", response_model=list[WorkflowSummary])
def list_workflows(request: Request) -> list[WorkflowSummary]:
    return request.app.state.store.list()


@router.post("", response_model=Workflow, status_code=status.HTTP_201_CREATED)
def create_workflow(body: WorkflowIn, request: Request) -> Workflow:
    return request.app.state.store.create(body)


@router.get("/{workflow_id}", response_model=Workflow)
def get_workflow(workflow_id: str, request: Request) -> Workflow:
    try:
        return request.app.state.store.get(workflow_id)
    except WorkflowNotFound:
        raise _not_found(workflow_id) from None


@router.put("/{workflow_id}", response_model=Workflow)
def update_workflow(workflow_id: str, body: WorkflowIn, request: Request) -> Workflow:
    try:
        return request.app.state.store.update(workflow_id, body)
    except WorkflowNotFound:
        raise _not_found(workflow_id) from None


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workflow(workflow_id: str, request: Request) -> Response:
    try:
        request.app.state.store.delete(workflow_id)
    except WorkflowNotFound:
        raise _not_found(workflow_id) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{workflow_id}/run", response_model=RunResult)
async def run_workflow(workflow_id: str, request: Request) -> RunResult:
    try:
        workflow = request.app.state.store.get(workflow_id)
    except WorkflowNotFound:
        raise _not_found(workflow_id) from None
    try:
        return await request.app.state.executor.run(workflow, workflow_id=workflow_id)
    except (
        WorkflowError
    ) as exc:  # cycle / bad graph: the request is unprocessable, not a server bug
        raise HTTPException(422, str(exc)) from exc
