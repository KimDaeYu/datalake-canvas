# Contributing to DataLake Canvas

Thanks for helping! The project is young, so small, focused contributions are the easiest to review
and merge. Browse [`docs/good-first-issues.md`](docs/good-first-issues.md) for starting points.

By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md). Contributions are licensed
under [Apache-2.0](LICENSE).

## Ground rules

* Open an issue before large changes so we can agree on the approach.
* Keep PRs small and single-purpose; include tests.
* **Never commit secrets** (API keys, DSNs, real data). Use `.env` (git-ignored) and `.env.example`.
* Don't weaken the read-only default. Changes to `backend/datalake_canvas/safety.py` must come with
  tests for both the newly allowed and the still-blocked cases.

## Development setup

You need Python 3.11+, Node 20+ (22 recommended) and, optionally, Docker.

```bash
python -m venv .venv && source .venv/bin/activate
make setup          # pip install -e "backend[dev]" + npm install
make demo-db        # builds examples/demo-data/demo.db
make backend        # http://localhost:8000/docs
make frontend       # http://localhost:5173   (in a second terminal)
```

Or run everything with `docker compose up --build` (UI on <http://localhost:8080>).

## Before you open a PR

```bash
make lint
make test
```

which runs `ruff check`, `ruff format --check`, `pytest backend`, and in `frontend/`:
`eslint`, `prettier --check`, `tsc --noEmit` and `vitest`. CI runs the same checks. `make fmt`
auto-fixes formatting.

## Where things live

| Area | Path | Notes |
| --- | --- | --- |
| Backend | `backend/datalake_canvas/` | FastAPI, executor, safety guard, MCP client, agent |
| Frontend | `frontend/src/` | React Flow canvas, side panel, API client |
| MCP servers | `mcp-servers/` | Reference servers (PostgreSQL, SQLite) |
| Docs | `docs/` | Architecture, adding data sources |

See [`docs/architecture.md`](docs/architecture.md) for the big picture and
[`docs/data-sources.md`](docs/data-sources.md) to add a data source.

## Commit and PR style

* Imperative, descriptive commit subjects (`Add sort transform`, `Fix cycle error message`).
* Fill in the PR template; explain *why*, not just *what*.
* Be kind in reviews, and expect reviewers to be too.

## Reporting bugs and security issues

Use the issue templates for bugs and feature requests. For vulnerabilities see
[SECURITY.md](SECURITY.md); do not file a public issue.
