import type { NodeTypes } from "@xyflow/react";
import { ChartNode } from "./ChartNode";
import { DataSourceNode } from "./DataSourceNode";
import { QueryNode } from "./QueryNode";
import { TransformNode } from "./TransformNode";

/** Keys match the backend's NodeType values. Defined at module level so React Flow gets a stable object. */
export const nodeTypes = {
  data_source: DataSourceNode,
  query: QueryNode,
  transform: TransformNode,
  chart: ChartNode,
} satisfies NodeTypes;
