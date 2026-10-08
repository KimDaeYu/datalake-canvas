import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { CanvasNode, DataSourceInfo, TableInfo } from "../types";
import { inputClass } from "./fields";

interface Props {
  datasources: DataSourceInfo[];
  selected: CanvasNode | undefined;
  onInsert: (tableName: string) => void;
}

// A fetch result is tagged with the data source it belongs to, so a stale result is never shown.
type Loaded = { id: string; tables: TableInfo[] } | { id: string; error: string };

/** Lists tables and columns of a data source; clicking a table inserts its name into the selected Query node. */
export function SchemaBrowser({ datasources, selected, onInsert }: Props) {
  const [picked, setPicked] = useState("");
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [expanded, setExpanded] = useState<{ id: string; names: Set<string> }>({
    id: "",
    names: new Set(),
  });

  // Follow a selected Data Source node; otherwise keep the manual pick, else the first source.
  const fromNode =
    selected?.type === "data_source" ? String(selected.data.datasource_id ?? "") : "";
  const datasourceId = fromNode || picked || datasources[0]?.id || "";

  // Derived instead of stored: no synchronous setState inside the effect.
  const current = loaded?.id === datasourceId ? loaded : null;
  const loading = Boolean(datasourceId) && current === null;
  const open = expanded.id === datasourceId ? expanded.names : new Set<string>();

  useEffect(() => {
    if (!datasourceId) return;
    let cancelled = false;
    api
      .getSchema(datasourceId)
      .then((tables) => !cancelled && setLoaded({ id: datasourceId, tables }))
      .catch(
        (e) =>
          !cancelled &&
          setLoaded({ id: datasourceId, error: e instanceof Error ? e.message : String(e) }),
      );
    return () => {
      cancelled = true;
    };
  }, [datasourceId]);

  const canInsert = selected?.type === "query";
  const toggle = (name: string) => {
    const next = new Set(open);
    if (!next.delete(name)) next.add(name);
    setExpanded({ id: datasourceId, names: next });
  };

  return (
    <section className="space-y-2">
      <h2 className="text-sm font-semibold text-slate-800">Schema</h2>
      <select
        aria-label="Schema data source"
        className={inputClass}
        value={datasourceId}
        disabled={Boolean(fromNode)}
        onChange={(e) => setPicked(e.target.value)}
      >
        {datasources.length === 0 && <option value="">No data sources</option>}
        {datasources.map((ds) => (
          <option key={ds.id} value={ds.id}>
            {ds.name}
          </option>
        ))}
      </select>
      {loading && <p className="text-xs text-slate-500">Loading schema…</p>}
      {current && "error" in current && <p className="text-xs text-red-600">{current.error}</p>}
      {current &&
        "tables" in current &&
        (current.tables.length === 0 ? (
          <p className="text-xs text-slate-500">No tables found.</p>
        ) : (
          <>
            <p className="text-xs text-slate-500">
              {canInsert
                ? "Click a table name to add it to the selected query."
                : "Select a Query node to insert table names."}
            </p>
            <ul className="max-h-56 space-y-1 overflow-y-auto text-sm">
              {current.tables.map((t) => (
                <li key={t.name}>
                  <div className="flex items-center gap-1">
                    <button
                      aria-label={`${open.has(t.name) ? "Collapse" : "Expand"} ${t.name}`}
                      aria-expanded={open.has(t.name)}
                      className="w-4 text-xs text-slate-500"
                      onClick={() => toggle(t.name)}
                    >
                      {open.has(t.name) ? "▾" : "▸"}
                    </button>
                    <button
                      className="truncate rounded px-1 font-mono text-xs text-slate-800 enabled:hover:bg-indigo-50 disabled:cursor-default"
                      disabled={!canInsert}
                      title={canInsert ? `Insert ${t.name}` : "Select a Query node first"}
                      onClick={() => onInsert(t.name)}
                    >
                      {t.name}
                    </button>
                    <span className="text-xs text-slate-400">{t.columns.length}</span>
                  </div>
                  {open.has(t.name) && (
                    <ul className="ml-6 font-mono text-xs text-slate-600">
                      {t.columns.map((c) => (
                        <li key={c.name}>
                          {c.name} <span className="text-slate-400">{c.type}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </li>
              ))}
            </ul>
          </>
        ))}
    </section>
  );
}
