import { Handle, Position } from "@xyflow/react";
import { useContext } from "react";
import { RunContext } from "../state/RunContext";
import type { NodeKind } from "../types";

// Full class names (not interpolated) so Tailwind can see them.
const STYLES: Record<NodeKind, { badge: string; ring: string; name: string }> = {
  data_source: {
    badge: "bg-emerald-100 text-emerald-800",
    ring: "border-emerald-300",
    name: "Data Source",
  },
  query: { badge: "bg-sky-100 text-sky-800", ring: "border-sky-300", name: "Query" },
  transform: { badge: "bg-amber-100 text-amber-800", ring: "border-amber-300", name: "Transform" },
  chart: { badge: "bg-violet-100 text-violet-800", ring: "border-violet-300", name: "Chart" },
};

const STATUS_DOT = {
  success: "bg-emerald-500",
  error: "bg-red-500",
  skipped: "bg-slate-300",
} as const;

interface Props {
  id: string;
  kind: NodeKind;
  title: string;
  summary: string;
  selected?: boolean;
}

export function BaseNode({ id, kind, title, summary, selected }: Props) {
  const status = useContext(RunContext)[id]?.status;
  const style = STYLES[kind];
  return (
    <div
      className={`w-64 rounded-lg border bg-white shadow-sm ${style.ring} ${
        selected ? "ring-2 ring-indigo-500" : ""
      }`}
    >
      {kind !== "data_source" && <Handle type="target" position={Position.Left} />}
      <div className="flex items-center justify-between gap-2 border-b border-slate-100 px-3 py-2">
        <span
          className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${style.badge}`}
        >
          {style.name}
        </span>
        {status && (
          <span
            title={status}
            className={`h-2.5 w-2.5 rounded-full ${STATUS_DOT[status]}`}
            aria-label={`status: ${status}`}
          />
        )}
      </div>
      <div className="px-3 py-2">
        <div className="truncate text-sm font-medium text-slate-900">{title || style.name}</div>
        <div className="mt-1 line-clamp-2 break-words text-xs text-slate-500">{summary}</div>
      </div>
      {kind !== "chart" && <Handle type="source" position={Position.Right} />}
    </div>
  );
}
