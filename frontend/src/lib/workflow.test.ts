import { describe, expect, it } from "vitest";
import type { PlanResponse } from "../types";
import {
  createNode,
  fromPayload,
  parseWorkflowJson,
  planToNodes,
  serializeWorkflow,
  starterWorkflow,
  toPayload,
} from "./workflow";

describe("payload conversion", () => {
  it("round-trips the starter workflow through JSON", () => {
    const { nodes, edges } = starterWorkflow();
    const payload = toPayload("Starter", nodes, edges);
    const reparsed = parseWorkflowJson(serializeWorkflow(payload));
    expect(reparsed).toEqual(payload);

    const back = fromPayload(reparsed);
    expect(back.nodes.map((n) => n.id)).toEqual(["ds", "q", "chart"]);
    expect(back.edges).toHaveLength(2);
  });

  it("drops runtime-only React Flow fields when saving", () => {
    const node = {
      ...createNode("query", { x: 1, y: 2 }),
      selected: true,
      measured: { width: 1, height: 1 },
    };
    const [saved] = toPayload("w", [node], []).nodes;
    expect(Object.keys(saved).sort()).toEqual(["data", "id", "position", "type"]);
  });
});

describe("parseWorkflowJson", () => {
  const base = {
    name: "w",
    nodes: [{ id: "a", type: "query", data: { sql: "SELECT 1" } }],
    edges: [],
  };

  it("accepts a minimal workflow and fills defaults", () => {
    const wf = parseWorkflowJson(JSON.stringify(base));
    expect(wf.nodes[0].position).toEqual({ x: 0, y: 0 });
  });

  it.each([
    ["not json", "{"],
    ["no name", JSON.stringify({ ...base, name: "" })],
    ["unknown type", JSON.stringify({ ...base, nodes: [{ id: "a", type: "python" }] })],
    ["duplicate ids", JSON.stringify({ ...base, nodes: [base.nodes[0], base.nodes[0]] })],
    ["dangling edge", JSON.stringify({ ...base, edges: [{ source: "a", target: "zzz" }] })],
  ])("rejects %s", (_label, text) => {
    expect(() => parseWorkflowJson(text)).toThrow();
  });
});

describe("planToNodes", () => {
  const plan = (chart: PlanResponse["plan"]["chart"]): PlanResponse => ({
    datasource_id: "demo-sqlite",
    plan: { sql: "SELECT 1", explanation: "", chart },
    safety: { allowed: true, reason: null },
  });

  it("builds DataSource -> Query -> Chart when a chart is suggested", () => {
    const { nodes, edges } = planToNodes(plan({ chart_type: "line", x: "d", y: "n" }), {
      x: 0,
      y: 0,
    });
    expect(nodes.map((n) => n.type)).toEqual(["data_source", "query", "chart"]);
    expect(edges.map((e) => [e.source, e.target])).toEqual([
      [nodes[0].id, nodes[1].id],
      [nodes[1].id, nodes[2].id],
    ]);
    expect(nodes[1].data.sql).toBe("SELECT 1");
    expect(nodes[2].data).toMatchObject({ chart_type: "line", x: "d", y: "n" });
  });

  it("omits the chart when none is suggested", () => {
    expect(planToNodes(plan(null), { x: 0, y: 0 }).nodes).toHaveLength(2);
  });
});
