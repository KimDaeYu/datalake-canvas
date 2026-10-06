import type { NodeProps } from "@xyflow/react";
import type { CanvasNode } from "../types";
import { BaseNode } from "./BaseNode";

export function DataSourceNode({ id, data, selected }: NodeProps<CanvasNode>) {
  const ds = String(data.datasource_id ?? "");
  return (
    <BaseNode
      id={id}
      kind="data_source"
      title={data.label}
      selected={selected}
      summary={ds || "Choose a data source →"}
    />
  );
}
