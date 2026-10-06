import type { CanvasNode, DataSourceInfo } from "../types";
import { Field, inputClass } from "./fields";

interface Props {
  node: CanvasNode;
  datasources: DataSourceInfo[];
  onChange: (patch: Record<string, unknown>) => void;
}

const str = (v: unknown) => (v === undefined || v === null ? "" : String(v));

/** Config form for the selected node. Keys are snake_case to match the backend's node configs. */
export function NodeConfig({ node, datasources, onChange }: Props) {
  const d = node.data;
  return (
    <div className="space-y-3">
      <Field label="Label">
        <input
          className={inputClass}
          value={d.label}
          onChange={(e) => onChange({ label: e.target.value })}
        />
      </Field>

      {node.type === "data_source" && (
        <Field label="Data source">
          <select
            className={inputClass}
            value={str(d.datasource_id)}
            onChange={(e) => onChange({ datasource_id: e.target.value })}
          >
            <option value="">Select…</option>
            {datasources.map((ds) => (
              <option key={ds.id} value={ds.id}>
                {ds.name}
              </option>
            ))}
          </select>
        </Field>
      )}

      {node.type === "query" && (
        <Field label="SQL (read-only)">
          <textarea
            className={`${inputClass} h-40 font-mono text-xs`}
            value={str(d.sql)}
            spellCheck={false}
            onChange={(e) => onChange({ sql: e.target.value })}
          />
        </Field>
      )}

      {node.type === "transform" && (
        <>
          <Field label="Operation">
            <select
              className={inputClass}
              value={str(d.operation)}
              onChange={(e) => onChange({ operation: e.target.value })}
            >
              <option value="limit">Limit rows</option>
              <option value="select">Select columns</option>
              <option value="sort">Sort</option>
              <option value="filter">Filter</option>
            </select>
          </Field>
          {d.operation === "limit" && (
            <Field label="Number of rows">
              <input
                type="number"
                min={0}
                className={inputClass}
                value={str(d.n)}
                onChange={(e) =>
                  onChange({ n: e.target.value === "" ? "" : Number(e.target.value) })
                }
              />
            </Field>
          )}
          {d.operation === "select" && (
            <Field label="Columns (comma-separated)">
              <input
                className={inputClass}
                value={str(d.columns)}
                onChange={(e) => onChange({ columns: e.target.value })}
              />
            </Field>
          )}
          {(d.operation === "sort" || d.operation === "filter") && (
            <Field label="Column">
              <input
                className={inputClass}
                value={str(d.column)}
                onChange={(e) => onChange({ column: e.target.value })}
              />
            </Field>
          )}
          {d.operation === "sort" && (
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={Boolean(d.descending)}
                onChange={(e) => onChange({ descending: e.target.checked })}
              />
              Descending
            </label>
          )}
          {d.operation === "filter" && (
            <div className="grid grid-cols-[auto_1fr] gap-2">
              <select
                className={inputClass}
                value={str(d.op) || "=="}
                onChange={(e) => onChange({ op: e.target.value })}
              >
                {["==", "!=", ">", ">=", "<", "<=", "contains"].map((op) => (
                  <option key={op}>{op}</option>
                ))}
              </select>
              <input
                className={inputClass}
                placeholder="value"
                value={str(d.value)}
                onChange={(e) => onChange({ value: e.target.value })}
              />
            </div>
          )}
        </>
      )}

      {node.type === "chart" && (
        <>
          <Field label="Chart type">
            <select
              className={inputClass}
              value={str(d.chart_type) || "bar"}
              onChange={(e) => onChange({ chart_type: e.target.value })}
            >
              <option value="bar">Bar</option>
              <option value="line">Line</option>
            </select>
          </Field>
          <Field label="X column">
            <input
              className={inputClass}
              value={str(d.x)}
              onChange={(e) => onChange({ x: e.target.value })}
            />
          </Field>
          <Field label="Y column (numeric)">
            <input
              className={inputClass}
              value={str(d.y)}
              onChange={(e) => onChange({ y: e.target.value })}
            />
          </Field>
        </>
      )}
    </div>
  );
}
