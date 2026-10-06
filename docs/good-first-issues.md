# Good first issue ideas

Copy any of these into GitHub issues and label them `good first issue`. Each is scoped to a
small part of the codebase and has clear acceptance criteria.

1. **Add a `group_by` / aggregate transform** (backend, small)
   Extend `TransformConfig` and `apply_transform` in `backend/datalake_canvas/nodes.py` with a
   `aggregate` operation (group column + `sum|avg|count|min|max` of a value column), add the form
   fields in `frontend/src/components/NodeConfig.tsx` and unit tests in `tests/test_executor.py`.

2. **Show column suggestions in the Chart node form** (frontend, small)
   After a run, the upstream table's columns are known (`results` in `App.tsx`). Offer them as a
   `<datalist>` for the X/Y inputs in `NodeConfig.tsx`.

3. **Schema browser in the side panel** (frontend, medium)
   The backend already serves `GET /datasources/{id}/schema`. Render tables and columns for the
   selected data source, and let a click insert the table name into the Query node's SQL.

4. **Persist the selected data source in the prompt box** (frontend, small)
   Remember the last-used data source in `localStorage` and add a Vitest test for the helper.

5. **Add a MySQL MCP server** (`mcp-servers/mysql`, medium)
   Follow the contract in `docs/data-sources.md` (`list_tables`, `describe_table`, `run_select`),
   modeled on `mcp-servers/postgres/server.py`. Enforce read-only at the connection level and add
   a README plus a sample entry for `config/datasources.json`.

6. **Add an Anthropic provider behind `LLMProvider`** (backend, medium)
   Implement `LLMProvider.plan_query` in `backend/datalake_canvas/agent/anthropic_provider.py`,
   wire it into `create_provider`, and add a `DLC_ANTHROPIC_API_KEY` setting. Unit-test with a fake
   client; no network calls in tests.

7. **CSV download for table results** (frontend, small)
   Add a "Download CSV" button to `ResultView.tsx` with correct quoting/escaping, plus a pure
   `toCsv()` helper with tests in `src/lib/`.

8. **Keyboard shortcuts and undo/redo** (frontend, medium)
   `Ctrl/Cmd+S` to save, `Ctrl/Cmd+Enter` to run, and an undo stack for node/edge edits.

9. **Fuzz tests for the SQL safety guard** (backend, small-medium)
   Add property-based or table-driven tests with tricky inputs (nested comments, unicode
   whitespace, dollar quoting) to `tests/test_safety.py`; fix any bypass you find (see
   [SECURITY.md](../SECURITY.md) for how to report serious ones).
