import type {
  DataSourceInfo,
  Health,
  PlanResponse,
  RunResult,
  Workflow,
  WorkflowPayload,
  WorkflowSummary,
} from "../types";

const BASE: string = import.meta.env.VITE_API_BASE ?? "/api";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(BASE + path, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch {
    throw new ApiError(0, "Cannot reach the backend. Is it running?");
  }
  if (!res.ok) {
    let detail = res.statusText || `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (body?.detail) {
        detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      }
    } catch {
      // Non-JSON error body: keep the status text.
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const json = (body: unknown): RequestInit => ({ body: JSON.stringify(body) });

export const api = {
  health: () => request<Health>("/health"),
  listDatasources: () => request<DataSourceInfo[]>("/datasources"),
  listWorkflows: () => request<WorkflowSummary[]>("/workflows"),
  getWorkflow: (id: string) => request<Workflow>(`/workflows/${id}`),
  createWorkflow: (wf: WorkflowPayload) =>
    request<Workflow>("/workflows", { method: "POST", ...json(wf) }),
  updateWorkflow: (id: string, wf: WorkflowPayload) =>
    request<Workflow>(`/workflows/${id}`, { method: "PUT", ...json(wf) }),
  deleteWorkflow: (id: string) => request<void>(`/workflows/${id}`, { method: "DELETE" }),
  runWorkflow: (id: string) => request<RunResult>(`/workflows/${id}/run`, { method: "POST" }),
  agentQuery: (prompt: string, datasourceId: string) =>
    request<PlanResponse>("/agent/query", {
      method: "POST",
      ...json({ prompt, datasource_id: datasourceId }),
    }),
};
