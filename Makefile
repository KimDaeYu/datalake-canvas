.PHONY: setup demo-db backend frontend lint test fmt

# Run `source .venv/bin/activate` first (Python 3.11+).
setup:
	pip install -e "backend[dev]"
	cd frontend && npm install

demo-db:
	python examples/demo-data/build_demo_db.py

backend: demo-db
	uvicorn datalake_canvas.main:create_app --factory --reload --app-dir backend

frontend:
	cd frontend && npm run dev

lint:
	ruff check . && ruff format --check .
	cd frontend && npm run lint && npm run format:check && npm run typecheck

test:
	pytest backend
	cd frontend && npm test

fmt:
	ruff check --fix . && ruff format .
	cd frontend && npm run format
