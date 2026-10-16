import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ChevronDown, RefreshCw } from "lucide-react"
import { getReadOnlyJson } from "@/features/operator-data/operator-api"

type Settings = { autoresearch_effort: "light" | "standard" | "max"; optuna_trials_per_cycle: number }
const queryKey = ["workspace-research-settings"]
function settings(value: unknown): Settings {
  if (!value || typeof value !== "object") throw new Error("The research settings are incomplete.")
  const r = value as Record<string, unknown>
  if (!["light", "standard", "max"].includes(String(r.autoresearch_effort)) || typeof r.optuna_trials_per_cycle !== "number" || !Number.isInteger(r.optuna_trials_per_cycle) || r.optuna_trials_per_cycle < 1 || r.optuna_trials_per_cycle > 50) throw new Error("The research settings are incomplete.")
  return { autoresearch_effort: r.autoresearch_effort as Settings["autoresearch_effort"], optuna_trials_per_cycle: r.optuna_trials_per_cycle }
}

export function ResearchControls() {
  const client = useQueryClient()
  const report = useQuery({ queryKey, queryFn: async ({ signal }) => settings(await getReadOnlyJson<unknown>("/api/autoresearch/settings", signal)), staleTime: 60_000, retry: false })
  const [draft, setDraft] = useState<Settings | null>(null)
  const [apiKey, setApiKey] = useState("")
  const current = draft ?? report.data
  const mutation = useMutation({
    mutationFn: async (value: Settings) => {
      const response = await fetch("/api/autoresearch/settings", {
        method: "PATCH", credentials: "same-origin",
        headers: { "Content-Type": "application/json", ...(apiKey.trim() ? { "x-api-key": apiKey.trim() } : {}) },
        body: JSON.stringify(value),
      })
      if (response.status === 401 || response.status === 403) throw new Error("Operator access is required. Enter your API key and save again.")
      if (!response.ok) throw new Error("The settings could not be saved. Your changes are still here.")
      const saved = settings(await response.json())
      if (saved.autoresearch_effort !== value.autoresearch_effort || saved.optuna_trials_per_cycle !== value.optuna_trials_per_cycle) throw new Error("The server returned different settings. Reload to review the saved values.")
      return saved
    },
    onSuccess: saved => { client.setQueryData(queryKey, saved); setDraft(null); setApiKey("") },
  })
  const changed = !!current && !!report.data && (current.autoresearch_effort !== report.data.autoresearch_effort || current.optuna_trials_per_cycle !== report.data.optuna_trials_per_cycle)
  const valid = !!current && Number.isInteger(current.optuna_trials_per_cycle) && current.optuna_trials_per_cycle >= 1 && current.optuna_trials_per_cycle <= 50
  return <details className="lw-details lw-research-controls">
    <summary>Research controls<ChevronDown size={16}/></summary>
    <p>Saved settings apply when the next research run starts. A running optimizer session keeps its current trial count.</p>
    {report.isPending ? <p role="status">Reading saved settings…</p> : report.isError || !current ? <div><p role="alert">Research settings could not be loaded.</p><button className="lw-button" onClick={() => void report.refetch()}><RefreshCw size={14}/>Reload settings</button></div> : <form onSubmit={event => { event.preventDefault(); if (changed && valid && !mutation.isPending) mutation.mutate(current) }}>
      <div className="lw-settings-fields"><label>Research effort<select value={current.autoresearch_effort} disabled={mutation.isPending} onChange={event => { setDraft({ ...current, autoresearch_effort: event.target.value as Settings["autoresearch_effort"] }); mutation.reset() }}><option value="light">Light</option><option value="standard">Standard</option><option value="max">Maximum</option></select></label><label>Trials per cycle<input type="number" min={1} max={50} step={1} value={Number.isNaN(current.optuna_trials_per_cycle) ? "" : current.optuna_trials_per_cycle} disabled={mutation.isPending} onChange={event => { setDraft({ ...current, optuna_trials_per_cycle: event.target.value === "" ? NaN : Number(event.target.value) }); mutation.reset() }}/></label><label>Operator API key<input type="password" autoComplete="off" placeholder="If required by your server" value={apiKey} disabled={mutation.isPending} onChange={event => setApiKey(event.target.value)}/></label></div>
      <div className="lw-settings-actions"><button className="lw-button lw-primary" type="submit" disabled={!changed || !valid || mutation.isPending}>{mutation.isPending ? "Saving…" : "Save research settings"}</button>{changed && <button className="lw-button" type="button" disabled={mutation.isPending} onClick={() => { setDraft(null); mutation.reset(); setApiKey("") }}>Discard changes</button>}</div>
      {!valid && <p role="alert">Use a whole number from 1 to 50 trials.</p>}{mutation.isError && <p role="alert">{mutation.error.message}</p>}{mutation.isSuccess && <p role="status">Research settings saved.</p>}
    </form>}
  </details>
}
