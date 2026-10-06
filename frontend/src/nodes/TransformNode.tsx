import type { NodeProps } from "@xyflow/react";
import type { CanvasNode } from "../types";
import { BaseNode } from "./BaseNode";

function describe(data: CanvasNode["data"]): string {
  switch (data.operation) {
    case "limit":
      return `limit ${String(data.n ?? "?")}`;
    case "select":
      return `select ${String(data.columns ?? "…")}`;
    case "sort":
      return `sort by ${String(data.column ?? "…")}${data.descending ? " ↓" : " ↑"}`;
    case "filter":
      return `where ${String(data.column ?? "…")} ${String(data.op ?? "==")} ${String(data.value ?? "…")}`;
    default:
      return "Not configured";
  }
}

export function TransformNode({ id, data, selected }: NodeProps<CanvasNode>) {
  return (
    <BaseNode
      id={id}
      kind="transform"
      title={data.label}
      selected={selected}
      summary={describe(data)}
    />
  );
}
