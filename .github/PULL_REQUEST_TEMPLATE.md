## What and why

<!-- What does this change, and what problem does it solve? Link the issue: Closes # -->

## How it was tested

<!-- Commands you ran, screenshots for UI changes. -->

## Checklist

- [ ] `ruff check . && ruff format --check .` and `pytest backend` pass (if backend/MCP code changed)
- [ ] `npm run lint && npm run format:check && npm run typecheck && npm test` pass (if frontend changed)
- [ ] New behaviour has tests (the safety guard and executor especially)
- [ ] Docs updated (README / `docs/`) if user-facing behaviour changed
- [ ] No secrets, credentials or private data in the diff
- [ ] Nothing weakens the read-only default; any change to `safety.py` explains the reasoning
