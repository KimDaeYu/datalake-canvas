# Security Policy

DataLake Canvas is early-stage software (pre-1.0). It has had no external security audit.
Please treat it accordingly and do not expose it to the public internet or point it at
production databases with write access.

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

Use GitHub's private vulnerability reporting: go to the repository's **Security** tab and
choose **Report a vulnerability**. Include what you found, how to reproduce it and the
impact you see. We aim to acknowledge reports within a few days; this is a volunteer
project, so there is no formal SLA.

## Supported versions

Only the latest commit on `main` is supported until a first release is tagged.

## Security model (what to expect)

* **No authentication.** The API and UI have no login. Run it on localhost or behind your own
  authenticated reverse proxy. Anyone who can reach the API can run read queries against every
  configured data source.
* **Read-only by default.** The backend's SQL guard (`backend/datalake_canvas/safety.py`) blocks
  non-`SELECT` statements and multi-statement input. It is defense in depth, **not a SQL parser**,
  and should not be your only control.
* **Database-level protection comes from MCP servers.** The reference servers open read-only
  connections. Always connect with a database role that only has `SELECT` grants.
* **`DLC_ALLOW_WRITE_QUERIES=true` relaxes the backend guard.** It is off by default; enable it only
  with a data source whose MCP server and database role are intentionally writable.
* **LLM output is untrusted.** Agent-generated SQL passes through the same guard and is returned as a
  plan for you to review; it is not executed automatically. Table/column names and your prompt are sent
  to the configured LLM provider (OpenAI by default); row data is not.
* **Secrets** (API keys, DSNs) belong in environment variables / `.env`, never in committed files. The
  `/datasources` endpoint deliberately does not expose server commands or environment.
* **MCP servers are code you run.** A configured MCP server is launched as a subprocess with only the
  environment you list for it. Only register servers you trust.
