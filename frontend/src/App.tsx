import { getShortcutAction } from "./lib/shortcuts";

import {
  addEdge,
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  type Connection,
} from "@xyflow/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api/client";
import { SidePanel } from "./components/SidePanel";
import {
  createNode,
  fromPayload,
  NODE_KINDS,
  parseWorkflowJson,
  planToNodes,
  serializeWorkflow,
  starterWorkflow,
  toPayload,
} from "./lib/workflow";
import { nodeTypes } from "./nodes";
import { RunContext } from "./state/RunContext";
import type {
  CanvasEdge,
  CanvasNode,
  DataSourceInfo,
  Health,
  NodeKind,
  NodeResult,
  PlanResponse,
  WorkflowPayload,
  WorkflowSummary,
} from "./types";

type Notice = { kind: "info" | "error"; text: string };

const starter = starterWorkflow();
const buttonClass =
  "rounded border border-slate-300 bg-white px-2.5 py-1 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50";

function Canvas() {
  const [nodes, setNodes, onNodesChange] = useNodesState<CanvasNode>(starter.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState<CanvasEdge>(starter.edges);
  const [name, setName] = useState("Untitled workflow");
  const [workflowId, setWorkflowId] = useState<string | null>(null);
  const [results, setResults] = useState<Record<string, NodeResult>>({});
  const [datasources, setDatasources] = useState<DataSourceInfo[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [saved, setSaved] = useState<WorkflowSummary[]>([]);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [busy, setBusy] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const selected = nodes.find((n) => n.selected);

  const fail = (e: unknown) =>
    setNotice({ kind: "error", text: e instanceof Error ? e.message : String(e) });
  const refreshSaved = useCallback(
    () =>
      api
        .listWorkflows()
        .then(setSaved)
        .catch(() => setSaved([])),
    [],
  );

  useEffect(() => {
    api
      .health()
      .then(setHealth)
      .catch(() => setHealth(null));
    api
      .listDatasources()
      .then(setDatasources)
      .catch(() => setDatasources([]));
    void refreshSaved();
  }, [refreshSaved]);

  const onConnect = useCallback((c: Connection) => setEdges((eds) => addEdge(c, eds)), [setEdges]);

  const addNode = (kind: NodeKind) => {
    const i = nodes.length;
    setNodes((ns) => [
      ...ns.map((n) => ({ ...n, selected: false })),
      {
        ...createNode(kind, { x: 60 + (i % 4) * 300, y: 60 + Math.floor(i / 4) * 190 }),
        selected: true,
      },
    ]);
  };

  const updateNode = (id: string, patch: Record<string, unknown>) =>
    setNodes((ns) => ns.map((n) => (n.id === id ? { ...n, data: { ...n.data, ...patch } } : n)));

  const addPlan = (resp: PlanResponse) => {
    const maxY = nodes.reduce((m, n) => Math.max(m, n.position.y), 0);
    const added = planToNodes(resp, { x: 60, y: maxY + 200 });
    setNodes((ns) => [...ns.map((n) => ({ ...n, selected: false })), ...added.nodes]);
    setEdges((es) => [...es, ...added.edges]);
  };

  const load = (wf: WorkflowPayload, id: string | null) => {
    const next = fromPayload(wf);
    setNodes(next.nodes);
    setEdges(next.edges);
    setName(wf.name);
    setWorkflowId(id);
    setResults({});
  };

  const save = async (): Promise<string> => {
    const payload = toPayload(name, nodes, edges);
    const wf = workflowId
      ? await api.updateWorkflow(workflowId, payload)
      : await api.createWorkflow(payload);
    setWorkflowId(wf.id);
    void refreshSaved();
    return wf.id;
  };

  const guarded = (fn: () => Promise<void>) => async () => {
    setBusy(true);
    setNotice(null);
    try {
      await fn();
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  };

  const onSave = guarded(async () => {
    await save();
    setNotice({ kind: "info", text: "Saved." });
  });

  const onRun = guarded(async () => {
    const id = await save(); // the backend runs the stored copy
    const run = await api.runWorkflow(id);
    setResults(run.results);
    const bad = Object.values(run.results).filter((r) => r.status === "error").length;
    setNotice(
      bad
        ? {
            kind: "error",
            text: `${bad} node${bad > 1 ? "s" : ""} failed. Select a node to see why.`,
          }
        : { kind: "info", text: "Run finished." },
    );
  });

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      const action = getShortcutAction(event);
      if (!action || busy || event.repeat) return;

      event.preventDefault();

      if (action === "save") {
        void onSave();
      } else {
        void onRun();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [busy, onSave, onRun]);

  const onOpen = (id: string) =>
    guarded(async () => {
      if (id) load(await api.getWorkflow(id), id);
    })();

  const onExport = () => {
    const blob = new Blob([serializeWorkflow(toPayload(name, nodes, edges))], {
      type: "application/json",
    });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${name.replace(/[^\w.-]+/g, "_") || "workflow"}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  const onImport = async (file: File | undefined) => {
    if (!file) return;
    try {
      load(parseWorkflowJson(await file.text()), null);
      setNotice({ kind: "info", text: `Imported “${file.name}”. Save to store it on the server.` });
    } catch (e) {
      fail(e);
    }
    if (fileInput.current) fileInput.current.value = "";
  };

  const runContext = useMemo(() => results, [results]);

  return (
    <div className="flex h-screen flex-col bg-slate-50 text-slate-900">
      <header className="flex flex-wrap items-center gap-2 border-b border-slate-200 bg-white px-4 py-2">
        <span className="mr-2 text-base font-semibold">DataLake Canvas</span>
        <input
          aria-label="Workflow name"
          className="w-56 rounded border border-slate-300 px-2 py-1 text-sm"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <div className="ml-2 flex gap-1" role="group" aria-label="Add node">
          {NODE_KINDS.map((k) => (
            <button
              key={k.kind}
              className={buttonClass}
              title={k.hint}
              onClick={() => addNode(k.kind)}
            >
              + {k.label}
            </button>
          ))}
        </div>
        <div className="ml-auto flex items-center gap-1">
          <select
            aria-label="Open saved workflow"
            className={buttonClass}
            value=""
            onChange={(e) => void onOpen(e.target.value)}
          >
            <option value="">Open…</option>
            {saved.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
          <button className={buttonClass} onClick={() => fileInput.current?.click()}>
            Import JSON
          </button>
          <button className={buttonClass} onClick={onExport}>
            Export JSON
          </button>
          <button
            className={buttonClass}
            disabled={busy}
            onClick={() => void onSave()}
            title="Save (Ctrl+S / Cmd+S)"
          >
            Save
          </button>
          <button
            className="rounded bg-emerald-600 px-3 py-1 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
            disabled={busy}
            onClick={() => void onRun()}
            title="Run (Ctrl+Enter / Cmd+Enter)"
          >
            {busy ? "Working…" : "Run"}
          </button>
          <input
            ref={fileInput}
            type="file"
            accept="application/json,.json"
            className="hidden"
            onChange={(e) => void onImport(e.target.files?.[0])}
          />
        </div>
      </header>

      {(notice || !health) && (
        <div
          role="status"
          className={`px-4 py-1.5 text-xs ${
            notice?.kind === "info" ? "bg-emerald-50 text-emerald-800" : "bg-red-50 text-red-700"
          }`}
        >
          {notice?.text ??
            "Cannot reach the backend. Start it with `docker compose up` or see the README."}
        </div>
      )}

      <div className="flex min-h-0 flex-1">
        <main className="min-w-0 flex-1">
          <RunContext.Provider value={runContext}>
            <ReactFlow
              nodes={nodes}
              edges={edges}
              nodeTypes={nodeTypes}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onConnect={onConnect}
              fitView
              deleteKeyCode={["Backspace", "Delete"]}
            >
              <Background />
              <Controls />
              <MiniMap pannable zoomable />
            </ReactFlow>
          </RunContext.Provider>
        </main>
        <SidePanel
          selected={selected}
          datasources={datasources}
          llmConfigured={health?.llm_configured ?? false}
          results={results}
          onChange={updateNode}
          onAddPlan={addPlan}
        />
      </div>
      {health?.read_only === false && (
        <div className="bg-amber-100 px-4 py-1 text-xs text-amber-900">
          Write queries are enabled on this backend (DLC_ALLOW_WRITE_QUERIES). The safety guard is
          relaxed.
        </div>
      )}
    </div>
  );
}

export default function App() {
  return (
    <ReactFlowProvider>
      <Canvas />
    </ReactFlowProvider>
  );
}
