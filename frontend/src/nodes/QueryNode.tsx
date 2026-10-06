import type { NodeProps } from "@xyflow/react";
import type { CanvasNode } from "../types";
import { BaseNode } from "./BaseNode";

export function QueryNode({ id, data, selected }: NodeProps<CanvasNode>) {
  const sql = String(data.sql ?? "").trim();
  return (
    <BaseNode
      id={id}
      kind="query"
      title={data.label}
      selected={selected}
      summary={sql || "No SQL yet"}
    />
  );
}
