import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { RefreshCw } from "lucide-react"
import { getMarketGenerationPolicy, MarketGenerationError, sameMarkets, saveMarketGenerationPolicy } from "./market-generation-api"
import "./market-generation-controls.css"

const queryKey = ["market-generation-policy"]
type Draft = { enabled: string[]; revision: string }

export function MarketGenerationControls() {
  const client = useQueryClient()
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState<Draft | null>(null)
  const [apiKey, setApiKey] = useState("")
  const policy = useQuery({ queryKey, queryFn: ({ signal }) => getMarketGenerationPolicy(signal), enabled: open, staleTime: 60_000, retry: false, refetchOnWindowFocus: false })
  const saved = policy.data
  const selected = draft?.enabled ?? saved?.enabled_markets ?? []
  const mutation = useMutation({ mutationFn: (value: { enabled_markets: string[]; expected_revision: string }) => saveMarketGenerationPolicy(value, apiKey), retry: false,
    onSuccess: value => { client.setQueryData(queryKey, value); setDraft(null) }, onSettled: () => setApiKey("") })
  const blocked = mutation.error instanceof MarketGenerationError && ["write_unavailable", "conflict", "unconfirmed", "validation"].includes(mutation.error.code)
  const changed = !!saved && (!saved.configured || !sameMarkets(selected, saved.enabled_markets))
  const reload = async () => {
    const result = await policy.refetch()
    if (result.isSuccess) { setDraft(null); setApiKey(""); mutation.reset() }
  }
  const summary = saved?.state === "unavailable" || policy.isError ? "Unavailable" : saved ? saved.configured ? `${saved.enabled_markets.length} selected` : "Existing defaults" : "Saved server policy"
  return <details className="md-market-settings md-generation-controls" onToggle={event => { setOpen(event.currentTarget.open); if (!event.currentTarget.open) setApiKey("") }}>
    <summary>Market generation <span>{summary}</span></summary>
    {!open ? null : policy.isPending ? <p role="status">Reading saved generation policy…</p> : policy.isError || !saved ? <div><p role="alert">The generation policy could not be loaded. Your visible market boards are still available.</p><button type="button" className="md-button" onClick={() => void reload()}><RefreshCw size={14}/>Reload generation policy</button></div> : saved.state === "unavailable" ? <div><p role="alert">Generation settings are unavailable. A valid saved policy must be restored before editing.</p><p>{saved.note}</p><button type="button" className="md-button" onClick={() => void reload()}><RefreshCw size={14}/>Reload generation policy</button></div> : <form onSubmit={event => { event.preventDefault(); if (changed && saved.editing_available && apiKey.trim() && !blocked && !mutation.isPending && !policy.isFetching) mutation.mutate({ enabled_markets: [...selected], expected_revision: draft?.revision ?? saved.revision }) }}>
      {!saved.editing_available && <p role="status">Saving is unavailable on this server. An operator must configure market-generation write access first.</p>}
      <p>Saved generation affects future selections. Browser visibility is separate.</p>
      {!saved.configured && <p>Using existing generation defaults.</p>}
      <fieldset disabled={!saved.editing_available || mutation.isPending || policy.isFetching}><legend>Markets allowed in future generation</legend>{saved.supported_markets.map((market,index) => <label key={market.id} className={!market.supported ? "md-generation-unsupported" : undefined}><input type="checkbox" aria-label={`Generate ${market.label}`} aria-describedby={!market.supported && market.reason ? `generation-reason-${index}` : undefined} checked={market.supported && selected.includes(market.id)} disabled={!market.supported} onChange={event => { const next = event.target.checked ? [...selected,market.id] : selected.filter(id => id !== market.id); setDraft({ enabled: saved.supported_markets.filter(m => m.supported && next.includes(m.id)).map(m => m.id), revision: draft?.revision ?? saved.revision }); if (!blocked) mutation.reset() }}/><span>{market.label}{!market.supported && <small id={`generation-reason-${index}`}>{market.reason || "Generation is not supported yet."}</small>}</span></label>)}</fieldset>
      {!selected.length && <p className="md-generation-empty">Future runs will produce rankings without market selections when this empty selection is saved.</p>}
      <p>{saved.note}</p>
      <label className="md-generation-key">Operator API key<input type="password" autoComplete="off" value={apiKey} disabled={!saved.editing_available || mutation.isPending} placeholder="Required to save" onChange={event => setApiKey(event.target.value)}/></label>
      <div className="md-generation-actions"><button type="submit" className="md-button md-button-primary" disabled={!saved.editing_available || !changed || !apiKey.trim() || !!blocked || mutation.isPending || policy.isFetching}>{mutation.isPending ? "Saving and confirming…" : "Save generation policy"}</button>{draft && <button type="button" className="md-button" disabled={mutation.isPending} onClick={() => { setDraft(null); setApiKey(""); if (!blocked) mutation.reset() }}>Discard draft</button>}<button type="button" className="md-button" disabled={mutation.isPending || policy.isFetching} onClick={() => void reload()}>{policy.isFetching ? "Reading…" : draft ? "Reload and discard draft" : "Reload saved policy"}</button></div>
      {mutation.isError && <p role="alert">{mutation.error.message}</p>}{mutation.isSuccess && <p role="status">Generation policy saved and confirmed. New runs will use this revision.</p>}
    </form>}
  </details>
}
