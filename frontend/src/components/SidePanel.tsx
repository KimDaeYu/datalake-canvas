import { appendToSql } from "../lib/workflow";
import type { CanvasNode, DataSourceInfo, NodeResult, PlanResponse } from "../types";
import { NodeConfig } from "./NodeConfig";
import { SchemaBrowser } from "./SchemaBrowser";
import { PromptBox } from "./PromptBox";
import { ResultView } from "./ResultView";

interface Props {
  selected: CanvasNode | undefined;
  datasources: DataSourceInfo[];
  llmConfigured: boolean;
  results: Record<string, NodeResult>;
  onChange: (id: string, patch: Record<string, unknown>) => void;
  onAddPlan: (plan: PlanResponse) => void;
}

export function SidePanel({
  selected,
  datasources,
  llmConfigured,
  results,
  onChange,
  onAddPlan,
}: Props) {
  return (
    <aside className="flex w-96 shrink-0 flex-col gap-6 overflow-y-auto border-l border-slate-200 bg-white p-4">
      <PromptBox datasources={datasources} llmConfigured={llmConfigured} onAddPlan={onAddPlan} />
      <hr className="border-slate-200" />
      <SchemaBrowser
        datasources={datasources}
        selected={selected}
        onInsert={(name) => {
          if (selected?.type === "query") {
            onChange(selected.id, { sql: appendToSql(String(selected.data.sql ?? ""), name) });
          }
        }}
      />
      <hr className="border-slate-200" />
      {selected ? (
        <>
          <section className="space-y-2">
            <h2 className="text-sm font-semibold text-slate-800">Node settings</h2>
            <NodeConfig
              node={selected}
              datasources={datasources}
              onChange={(patch) => onChange(selected.id, patch)}
            />
          </section>
          <section className="space-y-2">
            <h2 className="text-sm font-semibold text-slate-800">Output</h2>
            <ResultView result={results[selected.id]} />
          </section>
        </>
      ) : (
        <p className="text-sm text-slate-500">
          Select a node to edit it, or add one from the toolbar.
        </p>
      )}
    </aside>
  );
}
