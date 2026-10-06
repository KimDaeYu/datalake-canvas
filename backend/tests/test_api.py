import pytest
from fastapi.testclient import TestClient

from datalake_canvas.agent.base import ChartSuggestion, LLMProvider, PlanRequest, QueryPlan
from datalake_canvas.config import Settings
from datalake_canvas.main import create_app
from datalake_canvas.mcp_client import MCPServerSpec
from datalake_canvas.registry import DataSourceRegistry
from tests.conftest import FakeGateway


class FakeProvider(LLMProvider):
    name = "fake"

    def __init__(self, sql: str):
        self.sql = sql
        self.requests: list[PlanRequest] = []

    async def plan_query(self, request: PlanRequest) -> QueryPlan:
        self.requests.append(request)
        return QueryPlan(
            sql=self.sql,
            explanation="test",
            chart=ChartSuggestion(chart_type="bar", x="region", y="revenue"),
        )


def make_client(tmp_path, sales_table, provider=None, **settings):
    registry = DataSourceRegistry(
        [MCPServerSpec(id="demo", name="Demo", dialect="sqlite", command="x")]
    )
    gateway = FakeGateway({"SELECT 1": sales_table})
    app = create_app(
        Settings(workflows_dir=tmp_path / "wf", openai_api_key=None, **settings),
        gateway=gateway,
        registry=registry,
        provider=provider,
    )
    return TestClient(app)


@pytest.fixture
def client(tmp_path, sales_table):
    return make_client(tmp_path, sales_table)


WORKFLOW = {
    "name": "demo",
    "nodes": [
        {
            "id": "ds",
            "type": "data_source",
            "position": {"x": 0, "y": 0},
            "data": {"datasource_id": "demo"},
        },
        {"id": "q", "type": "query", "position": {"x": 200, "y": 0}, "data": {"sql": "SELECT 1"}},
    ],
    "edges": [{"id": "e", "source": "ds", "target": "q"}],
}


def test_health_reports_read_only(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["read_only"] is True
    assert body["llm_configured"] is False


def test_datasources_hide_launch_details(client):
    (ds,) = client.get("/datasources").json()
    assert ds == {"id": "demo", "name": "Demo", "description": "", "dialect": "sqlite"}


def test_workflow_crud_roundtrip(client):
    created = client.post("/workflows", json=WORKFLOW)
    assert created.status_code == 201
    wf_id = created.json()["id"]

    assert client.get(f"/workflows/{wf_id}").json()["name"] == "demo"
    assert [w["id"] for w in client.get("/workflows").json()] == [wf_id]

    updated = client.put(f"/workflows/{wf_id}", json={**WORKFLOW, "name": "renamed"})
    assert updated.json()["name"] == "renamed"
    assert updated.json()["created_at"] == created.json()["created_at"]

    assert client.delete(f"/workflows/{wf_id}").status_code == 204
    assert client.get(f"/workflows/{wf_id}").status_code == 404


@pytest.mark.parametrize("bad_id", ["nope", "../../etc/passwd", "0" * 32])
def test_unknown_or_malicious_ids_are_404(client, bad_id):
    assert client.get(f"/workflows/{bad_id}").status_code == 404
    assert client.post(f"/workflows/{bad_id}/run").status_code == 404


def test_invalid_graph_rejected(client):
    bad = {**WORKFLOW, "edges": [{"source": "ds", "target": "ghost"}]}
    assert client.post("/workflows", json=bad).status_code == 422


def test_run_workflow(client):
    wf_id = client.post("/workflows", json=WORKFLOW).json()["id"]
    run = client.post(f"/workflows/{wf_id}/run").json()
    assert run["status"] == "success"
    assert run["results"]["q"]["output"]["columns"] == ["region", "revenue"]


def test_run_cyclic_workflow_is_422(client):
    cyclic = {
        **WORKFLOW,
        "edges": [{"source": "ds", "target": "q"}, {"source": "q", "target": "ds"}],
    }
    wf_id = client.post("/workflows", json=cyclic).json()["id"]
    resp = client.post(f"/workflows/{wf_id}/run")
    assert resp.status_code == 422 and "cycle" in resp.json()["detail"]


def test_agent_without_provider_is_503(client):
    resp = client.post("/agent/query", json={"prompt": "hi", "datasource_id": "demo"})
    assert resp.status_code == 503
    assert "OPENAI_API_KEY" in resp.json()["detail"]


def test_agent_returns_validated_plan(tmp_path, sales_table):
    provider = FakeProvider("SELECT 1")
    client = make_client(tmp_path, sales_table, provider=provider)
    resp = client.post(
        "/agent/query", json={"prompt": "revenue by region", "datasource_id": "demo"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["plan"]["sql"] == "SELECT 1"
    assert body["plan"]["chart"]["chart_type"] == "bar"
    assert body["safety"] == {"allowed": True, "reason": None}
    assert provider.requests[0].dialect == "sqlite"
    assert "orders(id INTEGER)" in provider.requests[0].schema_text


def test_agent_flags_unsafe_plan(tmp_path, sales_table):
    client = make_client(tmp_path, sales_table, provider=FakeProvider("DROP TABLE orders"))
    body = client.post("/agent/query", json={"prompt": "x", "datasource_id": "demo"}).json()
    assert body["safety"]["allowed"] is False
    assert "DROP" in body["safety"]["reason"]


def test_agent_unknown_datasource(tmp_path, sales_table):
    client = make_client(tmp_path, sales_table, provider=FakeProvider("SELECT 1"))
    resp = client.post("/agent/query", json={"prompt": "x", "datasource_id": "nope"})
    assert resp.status_code == 404
