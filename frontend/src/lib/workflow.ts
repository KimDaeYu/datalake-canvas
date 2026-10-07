/** Pure helpers for converting between React Flow state, API payloads and JSON files. */
import type {
  ApiEdge,
  ApiNode,
  CanvasEdge,
  CanvasNode,
  CanvasNodeData,
  NodeKind,
  PlanResponse,
  WorkflowPayload,
} from "../types";

export const NODE_KINDS: { kind: NodeKind; label: string; hint: string }[] = [
  { kind: "data_source", label: "Data Source", hint: "Pick an MCP-backed database" },
  { kind: "query", label: "Query", hint: "Read-only SQL" },
  { kind: "transform", label: "Transform", hint: "Limit, select, sort, filter" },
  { kind: "chart", label: "Chart", hint: "Bar or line chart" },
];

export const isNodeKind = (v: unknown): v is NodeKind => NODE_KINDS.some((k) => k.kind === v);

export function newId(prefix: string): string {
  return `${prefix}_${Math.random().toString(36).slice(2, 8)}`;
}

export function defaultData(kind: NodeKind): CanvasNodeData {
  switch (kind) {
    case "data_source":
      return { label: "Data Source", datasource_id: "" };
    case "query":
      return { label: "Query", sql: "" };
    case "transform":
      return { label: "Transform", operation: "limit", n: 10 };
    case "chart":
      return { label: "Chart", chart_type: "bar", x: "", y: "" };
  }
}

export function createNode(
  kind: NodeKind,
  position: { x: number; y: number },
  data: Partial<CanvasNodeData> = {},
  id = newId(kind),
): CanvasNode {
  return { id, type: kind, position, data: { ...defaultData(kind), ...data } };
}

/** Only persisted fields leave the canvas (no `selected`, `measured`, ... runtime state). */
export function toPayload(name: string, nodes: CanvasNode[], edges: CanvasEdge[]): WorkflowPayload {
  return {
    name,
    nodes: nodes.map((n) => ({
      id: n.id,
      type: n.type as NodeKind,
      position: { x: n.position.x, y: n.position.y },
      data: { ...n.data },
    })),
    edges: edges.map((e) => ({ id: e.id, source: e.source, target: e.target })),
  };
}

export function fromPayload(wf: WorkflowPayload): { nodes: CanvasNode[]; edges: CanvasEdge[] } {
  return {
    nodes: wf.nodes.map((n) => ({
      id: n.id,
      type: n.type,
      position: n.position,
      data: { label: n.type, ...n.data } as CanvasNodeData,
    })),
    edges: wf.edges.map((e) => ({
      id: e.id ?? `e_${e.source}_${e.target}`,
      source: e.source,
      target: e.target,
    })),
  };
}

export const serializeWorkflow = (wf: WorkflowPayload): string => JSON.stringify(wf, null, 2);

const isRecord = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);

/** Parse and validate a workflow JSON file. Throws an Error with a user-readable message. */
export function parseWorkflowJson(text: string): WorkflowPayload {
  let raw: unknown;
  try {
    raw = JSON.parse(text);
  } catch {
    throw new Error("File is not valid JSON");
  }
  if (!isRecord(raw)) throw new Error("Workflow must be a JSON object");
  if (typeof raw.name !== "string" || !raw.name.trim()) throw new Error("Workflow needs a name");
  if (!Array.isArray(raw.nodes)) throw new Error("Workflow needs a 'nodes' array");

  const edgesRaw = raw.edges ?? [];
  if (!Array.isArray(edgesRaw)) throw new Error("'edges' must be an array");

  const nodes: ApiNode[] = raw.nodes.map((n: unknown, i: number) => {
    if (!isRecord(n) || typeof n.id !== "string" || !n.id)
      throw new Error(`Node #${i + 1} needs an id`);
    if (!isNodeKind(n.type)) throw new Error(`Node '${n.id}' has unknown type '${String(n.type)}'`);
    const pos = isRecord(n.position) ? n.position : {};
    return {
      id: n.id,
      type: n.type,
      position: {
        x: typeof pos.x === "number" ? pos.x : 0,
        y: typeof pos.y === "number" ? pos.y : 0,
      },
      data: isRecord(n.data) ? n.data : {},
    };
  });
  const ids = new Set(nodes.map((n) => n.id));
  if (ids.size !== nodes.length) throw new Error("Node ids must be unique");

  const edges: ApiEdge[] = edgesRaw.map((e: unknown, i: number) => {
    if (!isRecord(e) || typeof e.source !== "string" || typeof e.target !== "string")
      throw new Error(`Edge #${i + 1} needs 'source' and 'target'`);
    if (!ids.has(e.source) || !ids.has(e.target))
      throw new Error(`Edge ${e.source} -> ${e.target} references an unknown node`);
    return { id: typeof e.id === "string" ? e.id : null, source: e.source, target: e.target };
  });

  return { name: raw.name, nodes, edges };
}

/** Turn an agent plan into a ready-to-run DataSource -> Query (-> Chart) chain. */
export function planToNodes(
  resp: PlanResponse,
  origin: { x: number; y: number },
): { nodes: CanvasNode[]; edges: CanvasEdge[] } {
  const step = 320;
  const ds = createNode("data_source", origin, {
    label: "Data Source",
    datasource_id: resp.datasource_id,
  });
  const query = createNode(
    "query",
    { x: origin.x + step, y: origin.y },
    { label: "Agent query", sql: resp.plan.sql },
  );
  const nodes = [ds, query];
  const edges: CanvasEdge[] = [{ id: `e_${ds.id}_${query.id}`, source: ds.id, target: query.id }];
  if (resp.plan.chart) {
    const { chart_type, x, y } = resp.plan.chart;
    const chart = createNode(
      "chart",
      { x: origin.x + 2 * step, y: origin.y },
      { chart_type, x, y },
    );
    nodes.push(chart);
    edges.push({ id: `e_${query.id}_${chart.id}`, source: query.id, target: chart.id });
  }
  return { nodes, edges };
}

/** A small demo pipeline so the canvas is not empty on first load. */
export function starterWorkflow(): { nodes: CanvasNode[]; edges: CanvasEdge[] } {
  const ds = createNode(
    "data_source",
    { x: 40, y: 120 },
    { label: "Demo shop", datasource_id: "demo-sqlite" },
    "ds",
  );
  const q = createNode(
    "query",
    { x: 360, y: 120 },
    {
      label: "Orders per region",
      sql: "SELECT c.region, COUNT(*) AS orders FROM orders o JOIN customers c ON c.id = o.customer_id GROUP BY c.region",
    },
    "q",
  );
  const chart = createNode("chart", { x: 700, y: 120 }, { x: "region", y: "orders" }, "chart");
  return {
    nodes: [ds, q, chart],
    edges: [
      { id: "e_ds_q", source: "ds", target: "q" },
      { id: "e_q_chart", source: "q", target: "chart" },
    ],
  };
}

/** Appends an identifier to SQL, separated by a space unless the SQL is empty or already ends in whitespace. */
export function appendToSql(sql: string, identifier: string): string {
  if (!sql || /\s$/.test(sql)) return sql + identifier;
  return `${sql} ${identifier}`;
}
