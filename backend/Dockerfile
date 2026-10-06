# Build context is the repository root (see docker-compose.yml) so the MCP servers and demo
# data can be copied in alongside the backend.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY backend /app/backend
# psycopg is needed by the PostgreSQL MCP server, which the backend launches as a subprocess.
RUN pip install /app/backend "psycopg[binary]>=3.1"

COPY mcp-servers /app/mcp-servers
COPY config /app/config
COPY examples /app/examples

# Build the SQLite demo database from the committed SQL dump.
RUN mkdir -p /data/workflows \
 && python /app/examples/demo-data/build_demo_db.py --out /data/demo.db

ENV DLC_ROOT=/app \
    DLC_DATA_DIR=/data \
    DLC_WORKFLOWS_DIR=/data/workflows

# Run as an unprivileged user.
RUN useradd --system --uid 10001 dlc && chown -R dlc /data
USER dlc

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
CMD ["uvicorn", "datalake_canvas.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
