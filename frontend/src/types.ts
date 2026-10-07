import type { Edge, Node } from "@xyflow/react";

export type NodeKind = "data_source" | "query" | "transform" | "chart";

/** React Flow node payload: a label plus the node's config (snake_case keys, as the backend expects). */
export type CanvasNodeData = { label: string; [key: string]: unknown };
export type CanvasNode = Node<CanvasNodeData, NodeKind>;
export type CanvasEdge = Edge;

// ---- Backend API shapes (mirror backend/datalake_canvas/models.py) ----

export interface ApiNode {
  id: string;
  type: NodeKind;
  position: { x: number; y: number };
  data: Record<string, unknown>;
}

export interface ApiEdge {
  id?: string | null;
  source: string;
  target: string;
}

export interface WorkflowPayload {
  name: string;
  nodes: ApiNode[];
  edges: ApiEdge[];
}

export interface Workflow extends WorkflowPayload {
  id: string;
  created_at: string;
  updated_at: string;
}

export interface WorkflowSummary {
  id: string;
  name: string;
  node_count: number;
  updated_at: string;
}

export interface TableData {
  kind: "table";
  columns: string[];
  rows: unknown[][];
  truncated: boolean;
}

export interface DataSourceRef {
  kind: "datasource";
  datasource_id: string;
}

export interface ChartSpec {
  kind: "chart";
  chart_type: "bar" | "line";
  x: string;
  y: string;
  data: TableData;
}

export type NodeOutput = TableData | DataSourceRef | ChartSpec;

export interface NodeResult {
  node_id: string;
  status: "success" | "error" | "skipped";
  output: NodeOutput | null;
  error: string | null;
  duration_ms: number;
}

export interface RunResult {
  workflow_id: string | null;
  status: "success" | "failed";
  order: string[];
  results: Record<string, NodeResult>;
}

export interface DataSourceInfo {
  id: string;
  name: string;
  description: string;
  dialect: string;
}

export interface ColumnInfo {
  name: string;
  type?: string;
  [key: string]: unknown;
}

export interface TableInfo {
  name: string;
  columns: ColumnInfo[];
}

export interface Health {
  status: string;
  version: string;
  read_only: boolean;
  llm_configured: boolean;
}

export interface PlanResponse {
  datasource_id: string;
  plan: {
    sql: string;
    explanation: string;
    chart: { chart_type: "bar" | "line"; x: string; y: string } | null;
  };
  safety: { allowed: boolean; reason: string | null };
}
