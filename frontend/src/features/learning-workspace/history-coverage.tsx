import { useQuery } from "@tanstack/react-query"
import { ArrowDownToLine, ChevronDown } from "lucide-react"
import { getReadOnlyJson } from "@/features/operator-data/operator-api"
import { number, shortDate } from "./charts"
import type { HistoryCoverageReport } from "./types"

function readHistoryCoverage(value: unknown): HistoryCoverageReport {
  if (!value || typeof value !== "object") throw new Error("Source coverage is unavailable.")
  const r = value as Partial<HistoryCoverageReport>
  if (r.schema_version !== 1 || r.state !== "recovered_source_inventory" || !r.summary || ![r.summary.complete_card_versions, r.summary.named_event_labels].every(n => typeof n === "number" && Number.isFinite(n)) || !Array.isArray(r.events) || !r.events.every(e => e && typeof e.label === "string" && typeof e.card_versions === "number" && (e.first_generated === null || typeof e.first_generated === "string") && (e.last_generated === null || typeof e.last_generated === "string")) || !Array.isArray(r.gaps) || !r.gaps.every(s => typeof s === "string")) throw new Error("Source coverage is incomplete.")
  return r as HistoryCoverageReport
}

export function HistoryCoverage() {
  const report = useQuery({ queryKey: ["history-coverage"], queryFn: async ({ signal }) => readHistoryCoverage(await getReadOnlyJson<unknown>("/reports/history-coverage.json", signal)), staleTime: 300_000, retry: false })
  if (report.isPending) return <p className="lw-small lw-muted" role="status">Reading recovered source coverage…</p>
  if (report.isError || !report.data) return <p className="lw-small lw-muted">Recovered source coverage is unavailable. <button className="lw-plain-link" onClick={() => void report.refetch()}>Try again</button></p>
  const r = report.data
  return <section className="lw-history-coverage" aria-label="Recovered source coverage"><div><h2>Recovered history</h2><p><strong>{number(r.summary.complete_card_versions, 0)}</strong> card versions across <strong>{number(r.summary.named_event_labels, 0)}</strong> named event labels.</p><p className="lw-small lw-muted">This is source coverage. The performance record below uses only the selected reconciled cohort.</p></div>
    <details className="lw-details"><summary>Browse recovered event labels<ChevronDown size={16}/></summary><div className="lw-table-scroll"><table className="lw-data-table"><thead><tr><th>Source event label</th><th>Card versions</th><th>First generated</th><th>Last generated</th></tr></thead><tbody>{r.events.map(e => <tr key={e.label}><th scope="row">{e.label}</th><td>{number(e.card_versions, 0)}</td><td>{shortDate(e.first_generated ?? undefined)}</td><td>{shortDate(e.last_generated ?? undefined)}</td></tr>)}</tbody></table></div><p className="lw-small lw-muted">Labels and generation dates describe preserved sources. They do not certify pre-event publication or independent bets.</p>{r.gaps.length > 0 && <ul>{r.gaps.map(gap => <li key={gap}>{gap}</li>)}</ul>}<a className="lw-plain-link" href="/reports/history-coverage.json" download><ArrowDownToLine size={14}/>Download source coverage</a></details>
  </section>
}
