# DataLake Canvas frontend

React + TypeScript + Vite, [React Flow](https://reactflow.dev) (`@xyflow/react`) for the canvas, Tailwind CSS.

```bash
npm install
npm run dev        # http://localhost:5173, proxies /api -> http://localhost:8000
npm run lint && npm run format:check && npm run typecheck && npm test
npm run build
```

Set `VITE_API_PROXY` to point the dev proxy at a different backend.

| Path                  | Purpose                                                                       |
| --------------------- | ----------------------------------------------------------------------------- |
| `src/App.tsx`         | Canvas, toolbar, state, run/save/load flow                                    |
| `src/nodes/`          | The four custom node types (DataSource, Query, Transform, Chart)              |
| `src/components/`     | Side panel (node config + natural-language prompt), result views              |
| `src/lib/workflow.ts` | Pure helpers: React Flow <-> API conversion, JSON import/export (unit-tested) |
| `src/api/client.ts`   | Typed backend client                                                          |
