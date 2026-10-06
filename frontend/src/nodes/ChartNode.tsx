import type { NodeProps } from "@xyflow/react";
import type { CanvasNode } from "../types";
import { BaseNode } from "./BaseNode";

export function ChartNode({ id, data, selected }: NodeProps<CanvasNode>) {
  const x = String(data.x ?? "");
  const y = String(data.y ?? "");
  const summary =
    x && y ? `${String(data.chart_type ?? "bar")}: ${y} by ${x}` : "Set x and y columns →";
  return <BaseNode id={id} kind="chart" title={data.label} selected={selected} summary={summary} />;
}
