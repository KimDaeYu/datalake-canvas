import { useState } from "react";
import { api } from "../api/client";
import type { DataSourceInfo, PlanResponse } from "../types";
import { Field, inputClass } from "./fields";

interface Props {
  datasources: DataSourceInfo[];
  llmConfigured: boolean;
  onAddPlan: (plan: PlanResponse) => void;
}

/** Natural-language box: asks the agent for a query plan and lets the user drop it on the canvas. */
export function PromptBox({ datasources, llmConfigured, onAddPlan }: Props) {
  const [prompt, setPrompt] = useState("");
  const [datasourceId, setDatasourceId] = useState("");
  const [plan, setPlan] = useState<PlanResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const selected = datasourceId || datasources[0]?.id || "";

  async function ask() {
    setBusy(true);
    setError(null);
    setPlan(null);
    try {
      setPlan(await api.agentQuery(prompt, selected));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="space-y-2">
      <h2 className="text-sm font-semibold text-slate-800">Ask in plain language</h2>
      {!llmConfigured && (
        <p className="rounded bg-amber-50 p-2 text-xs text-amber-800">
          No LLM key configured. Set <code>OPENAI_API_KEY</code> in <code>.env</code> and restart
          the backend to enable this.
        </p>
      )}
      <Field label="Data source">
        <select
          className={inputClass}
          value={selected}
          onChange={(e) => setDatasourceId(e.target.value)}
        >
          {datasources.map((ds) => (
            <option key={ds.id} value={ds.id}>
              {ds.name}
            </option>
          ))}
        </select>
      </Field>
      <textarea
        className={`${inputClass} h-20`}
        placeholder="e.g. Total revenue by product category"
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
      />
      <button
        className="w-full rounded bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
        disabled={busy || !prompt.trim() || !selected}
        onClick={ask}
      >
        {busy ? "Thinking…" : "Generate query"}
      </button>
      {error && <p className="rounded bg-red-50 p-2 text-xs text-red-700">{error}</p>}
      {plan && (
        <div className="space-y-2 rounded border border-slate-200 p-2">
          <p className="text-xs text-slate-600">{plan.plan.explanation}</p>
          <pre className="overflow-auto rounded bg-slate-900 p-2 text-[11px] text-slate-100">
            {plan.plan.sql}
          </pre>
          {plan.safety.allowed ? (
            <button
              className="w-full rounded border border-indigo-600 px-3 py-1 text-sm font-medium text-indigo-700 hover:bg-indigo-50"
              onClick={() => onAddPlan(plan)}
            >
              Add to canvas
            </button>
          ) : (
            <p className="rounded bg-red-50 p-2 text-xs text-red-700">
              Blocked by the safety guard: {plan.safety.reason}
            </p>
          )}
        </div>
      )}
    </section>
  );
}
