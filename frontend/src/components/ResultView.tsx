import type { NodeResult, TableData } from "../types";
import { SimpleChart } from "./SimpleChart";
import { toCsv } from "../lib/csv";

const MAX_ROWS = 100;

function Table({ table }: { table: TableData }) {
  const handleDownloadCsv = () => {
    const csvString = toCsv(table.columns, table.rows);
    const blob = new Blob([csvString], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.setAttribute("download", "table_result.csv");
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <p className="text-[11px] text-slate-500">
          {table.rows.length} row{table.rows.length === 1 ? "" : "s"}
          {table.rows.length > MAX_ROWS && ` (showing first ${MAX_ROWS})`}
          {table.truncated && " · truncated by the row limit"}
        </p>
        <button
          onClick={handleDownloadCsv}
          className="rounded bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-700 hover:bg-slate-200 transition-colors"
        >
          Download CSV
        </button>
      </div>
      <div className="max-h-72 overflow-auto rounded border border-slate-200">
        <table className="w-full text-left text-xs">
          <thead className="sticky top-0 bg-slate-50">
            <tr>
              {table.columns.map((c) => (
                <th key={c} className="px-2 py-1 font-semibold text-slate-700">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {table.rows.slice(0, MAX_ROWS).map((row, i) => (
              <tr key={i} className="border-t border-slate-100">
                {row.map((cell, j) => (
                  <td key={j} className="whitespace-nowrap px-2 py-1 text-slate-800">
                    {cell === null ? <i className="text-slate-400">null</i> : String(cell)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function ResultView({ result }: { result: NodeResult | undefined }) {
  if (!result)
    return <p className="text-xs text-slate-500">Run the workflow to see this node’s output.</p>;
  if (result.status === "error")
    return <p className="rounded bg-red-50 p-2 text-xs text-red-700">{result.error}</p>;
  if (result.status === "skipped")
    return <p className="rounded bg-slate-100 p-2 text-xs text-slate-600">{result.error}</p>;

  const out = result.output;
  return (
    <div className="space-y-1">
      {out?.kind === "table" && <Table table={out} />}
      {out?.kind === "chart" && <SimpleChart spec={out} />}
      {out?.kind === "datasource" && (
        <p className="text-xs text-slate-600">
          Connected to <code>{out.datasource_id}</code>
        </p>
      )}
      <p className="text-[11px] text-slate-400">{result.duration_ms} ms</p>
    </div>
  );
}
