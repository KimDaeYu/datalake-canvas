# DataLake Canvas backend

FastAPI service that stores workflows, executes them (topological order), talks to
databases through MCP servers, and turns natural language into query plans.

```bash
# from the repo root
python -m venv .venv && source .venv/bin/activate   # Python 3.11+
pip install -e "backend[dev]"
python examples/demo-data/build_demo_db.py           # creates examples/demo-data/demo.db
uvicorn datalake_canvas.main:create_app --factory --reload --app-dir backend
```

API docs: http://localhost:8000/docs

```bash
ruff check . && ruff format --check .   # from repo root
pytest backend                           # or: cd backend && pytest
```

Layout:

| Module | Purpose |
| --- | --- |
| `config.py` | Environment-driven settings (`DLC_*`) |
| `models.py` | Pydantic schemas: workflow graph, node outputs, run results |
| `safety.py` | Read-only SQL guard |
| `executor.py`, `nodes.py` | Topological executor and per-node logic |
| `mcp_client.py`, `registry.py`, `gateway.py` | MCP client wrapper, pluggable data source registry, gateway used by the executor |
| `agent/` | `LLMProvider` interface, OpenAI Agents SDK provider, query planner |
| `store.py` | JSON-file workflow store |
| `routes/` | HTTP routes |
