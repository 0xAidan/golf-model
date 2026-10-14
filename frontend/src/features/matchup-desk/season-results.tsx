import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { ChevronDown, Download, ExternalLink, Info } from "lucide-react"
import { getReadOnlyJson } from "@/features/operator-data/operator-api"

export const SEASON_REPORT_PATH = "/reports/season-2026.json"
export const SEASON_DECISIONS_PATH = "/reports/season-2026-decisions.csv"

type MarketLane = {
  lane: string
  records: number
  events: number
  wins: number
  losses: number
  zero_return: number
  void: number
  ungraded: number
  conflicts: number
  incomplete: number
  missing_round?: number
  settled: number
  profit: number | null
  stake: number | null
  /** Stored profit / stored stake, not a percentage or flat-stake return. */
  roi: number | null
  selection_eligible: number
}
type SeasonEvent = {
  key: string
  name: string
  starts_on: string | null
  ends_on: string | null
  state: "elapsed" | "upcoming"
  records: number
  cards: number
  conflicts: number
  incomplete: number
  selection_eligible: number
  markets: Array<{ key: string; records: number; cards?: number }>
  source_url?: string
}
export type SeasonReport = {
  schema_version: 1
  as_of: string
  basis: "stored_paper_records"
  coverage: {
    source_generations: number
    core_observations: number
    pick_observations: number
    decision_groups: number
    calendar_elapsed_events: number
    events_with_picks: number
    events_with_cards: number
    unresolved_events: number
    conflict_groups: number
    incomplete_contract_groups: number
    selection_eligible: number
    unreadable_sources: number
    salvaged_observations: number
  }
  markets: Array<{ key: string; label: string; lanes: MarketLane[] }>
  events: SeasonEvent[]
  issues: Array<{ key: string; label: string; count: number }>
  selection: {
    status: string
    message: string
    protocol_id?: string
    minimum_earlier_events?: number
    minimum_later_events?: number
    minimum_later_decisions?: number
    rules: Array<{
      id: string
      label: string
      lane: string
      market: string
      model_variant: string
      eligible_decisions?: number
      eligible_events?: number
      earlier_events: number
      later_events: number
      later_decisions: number
      later_roi: number | null
      roi_interval: [number, number] | null
      sufficient: boolean
    }>
  }
  caveats: string[]
  provenance: { report_id: string; source_manifest_sha256: string; calendar_sha256: string }
}

const count = (n: number | null | undefined) => typeof n === "number" && Number.isFinite(n) ? n.toLocaleString() : "—"
const units = (n: number | null | undefined) => typeof n === "number" && Number.isFinite(n) ? `${n > 0 ? "+" : ""}${n.toFixed(2)}u` : "—"
const percent = (n: number | null | undefined) => typeof n === "number" && Number.isFinite(n) ? `${n > 0 ? "+" : ""}${(n * 100).toFixed(1)}%` : "—"
const variantLabel = (variant: string) => variant === "baseline" ? "Baseline" : variant
const calendarDate = (value: string | null | undefined, year = false) => {
  if (!value) return "Date unavailable"
  const d = new Date(`${value}T12:00:00Z`)
  return Number.isNaN(d.getTime()) ? "Date unavailable" : new Intl.DateTimeFormat("en", { month: "short", day: "numeric", ...(year ? { year: "numeric" as const } : {}), timeZone: "UTC" }).format(d)
}
const safeSource = (value: string | undefined) => {
  if (!value) return undefined
  try { const url = new URL(value); return url.protocol === "https:" ? url.href : undefined } catch { return undefined }
}

async function loadSeasonReport(signal?: AbortSignal): Promise<SeasonReport> {
  const report = await getReadOnlyJson<SeasonReport>(SEASON_REPORT_PATH, signal)
  if (report?.schema_version !== 1 || report?.basis !== "stored_paper_records" || !report.coverage || !Array.isArray(report.markets) || !Array.isArray(report.events) || !Array.isArray(report.issues) || !report.provenance || !report.selection || !Array.isArray(report.selection.rules) || !Array.isArray(report.caveats)) {
    throw new Error("The season report could not be read.")
  }
  return report
}

function MarketSelect({ report, market, onChange, label, allowAll = true }: { report: SeasonReport; market: string | null; onChange: (market: string | null) => void; label: string; allowAll?: boolean }) {
  return <label className="md-season-scope-control md-select"><span>Market</span><select aria-label={label} value={market || ""} onChange={event => onChange(event.target.value || null)}>{allowAll && <option value="">All markets</option>}{report.markets.map(item => <option key={item.key} value={item.key}>{item.label}</option>)}</select></label>
}

function EventCoverage({ report, market, onMarketChange }: { report: SeasonReport; market: string | null; onMarketChange: (market: string | null) => void }) {
  const [selectedKey, setSelectedKey] = useState<string | null>(null)
  const selected = report.events.find(event => event.key === selectedKey) || report.events.find(event => event.records > 0) || report.events[0]
  const marketLabel = report.markets.find(item => item.key === market)?.label
  const records = (event: SeasonEvent) => market === null ? event.records : (event.markets.find(item => item.key === market)?.records ?? 0)
  const cards = (event: SeasonEvent) => market === null ? event.cards : event.markets.find(item => item.key === market)?.cards
  const state = (event: SeasonEvent) => event.state === "upcoming" ? "Upcoming" : records(event) > 0 ? "Records recovered" : (cards(event) || 0) > 0 ? "Archived card only" : "No reconciled picks"
  const source = safeSource(selected?.source_url)
  return (
    <section className="md-season-coverage" aria-labelledby="season-coverage-title">
      <div className="md-season-subheading">
        <div>
          <h2 id="season-coverage-title">Where the record reaches.</h2>
          <p>{marketLabel || "All markets"} · Both model lanes · Each mark is one calendar event.</p>
        </div>
        <MarketSelect report={report} market={market} onChange={onMarketChange} label="Event coverage market" />
      </div>
      <p className="md-season-coverage-count">{count(report.events.filter(event => event.state === "elapsed" && records(event) > 0).length)} events with reconciled picks / {count(report.coverage.calendar_elapsed_events)} elapsed</p>
      {report.events.length ? <>
        <p className="md-sr-only" id="season-strip-keys">Use the left and right arrow keys to inspect adjacent events. Home and End move to the first and last event.</p>
        <div className="md-season-strip" role="group" aria-label={`${marketLabel || "All markets"} event coverage`} aria-describedby="season-strip-keys">
          {report.events.map((event, index) => <button
            key={event.key}
            type="button"
            className={event.state === "upcoming" ? "is-upcoming" : records(event) > 0 ? "has-records" : (cards(event) || 0) > 0 ? "has-cards" : "is-missing"}
            aria-label={`${event.name}, ${calendarDate(event.starts_on)}, ${count(records(event))} recovered records, ${state(event)}`}
            aria-pressed={selected?.key === event.key}
            tabIndex={selected?.key === event.key ? 0 : -1}
            title={`${event.name} · ${count(records(event))} records · ${state(event)}`}
            onClick={() => setSelectedKey(event.key)}
            onKeyDown={key => {
              const next = key.key === "ArrowRight" ? Math.min(index + 1, report.events.length - 1) : key.key === "ArrowLeft" ? Math.max(index - 1, 0) : key.key === "Home" ? 0 : key.key === "End" ? report.events.length - 1 : null
              if (next === null) return
              key.preventDefault()
              setSelectedKey(report.events[next].key)
              key.currentTarget.parentElement?.querySelectorAll("button")[next]?.focus()
            }}
          ><span /></button>)}
        </div>
        <div className="md-season-strip-key" aria-hidden="true">
          <span>{calendarDate(report.events[0]?.starts_on)}</span>
          <div><span className="has-records">Records</span><span className="has-cards">Card only</span><span className="is-missing">Missing</span><span className="is-upcoming">Upcoming</span></div>
          <span>{calendarDate(report.events.at(-1)?.ends_on)}</span>
        </div>
        {selected && <div className="md-season-event" aria-live="polite">
          <div>
            <h3>{selected.name}</h3>
            <p>{calendarDate(selected.starts_on)} – {calendarDate(selected.ends_on)} · {state(selected)}</p>
            {source && <a className="md-text-link" href={source} target="_blank" rel="noreferrer">Official event dates <ExternalLink size={13} /></a>}
          </div>
          <dl>
            <div><dt>{marketLabel || "All market"} records</dt><dd>{count(records(selected))}</dd></div>
            <div><dt>{market ? "This market’s archived card rows" : "Archived card rows"}</dt><dd>{count(cards(selected))}</dd></div>
            <div><dt>Conflicting groups</dt><dd>{count(selected.conflicts)}</dd></div>
            <div><dt>Selection eligible</dt><dd>{count(selected.selection_eligible)}</dd></div>
          </dl>
          <p className="md-season-event-note">Conflicts and selection eligibility cover all markets in this event. Archived cards are source evidence, not settled records or proof a bet was placed.</p>
        </div>}
        <details className="md-season-details md-season-event-list">
          <summary>Browse all {count(report.events.length)} calendar events <ChevronDown size={16} /></summary>
          <div className="md-season-table-wrap">
            <table className="md-season-events-table">
              <caption className="md-sr-only">Calendar coverage for {marketLabel || "all markets"}, both model lanes</caption>
              <thead><tr><th>Event</th><th>Dates</th><th>Records</th><th>Coverage</th></tr></thead>
              <tbody>{report.events.map(event => <tr key={event.key}>
                <th scope="row"><button className="md-season-market-button" onClick={() => setSelectedKey(event.key)}>{event.name}</button></th>
                <td>{calendarDate(event.starts_on)} – {calendarDate(event.ends_on)}</td>
                <td>{count(records(event))}</td>
                <td>{state(event)}</td>
              </tr>)}</tbody>
            </table>
          </div>
        </details>
      </> : <p className="md-muted">The event calendar is unavailable in this snapshot.</p>}
    </section>
  )
}

export function SeasonResults() {
  const [lane, setLane] = useState("dashboard")
  const [market, setMarket] = useState<string | null>(null)
  const [preferredVariant, setPreferredVariant] = useState("baseline")
  const query = useQuery({ queryKey: ["season-results", "2026"], queryFn: ({ signal }) => loadSeasonReport(signal), staleTime: 300_000, retry: false })
  const report = query.data
  const researchMarket = market || "72h"
  const researchLabel = report?.markets.find(item => item.key === researchMarket)?.label || researchMarket
  const scopedRules = report?.selection.rules.filter(rule => rule.lane === lane && rule.market === researchMarket && typeof rule.model_variant === "string" && rule.model_variant.length > 0) || []
  const variants = [...new Set(scopedRules.map(rule => rule.model_variant))].sort((a, b) => a === "baseline" ? -1 : b === "baseline" ? 1 : a.localeCompare(b))
  const variant = variants.includes(preferredVariant) ? preferredVariant : variants[0]
  const rules = scopedRules.filter(rule => rule.model_variant === variant)
  const scopeBaseline = rules.find(rule => rule.id === "baseline") || rules[0]
  const selectionMessage = report?.selection.message.replace(/^No rule promoted\.\s*/i, "") || "Selection research is pending enough eligible event history."
  return <section className="md-single-page md-season-results" aria-labelledby="season-title">
    <div className="md-section-title">
      <div><h1 id="season-title">The season, market by market.</h1><p>Recovered picks, original outcomes, and the gaps that matter.</p></div>
      {report && <div className="md-season-snapshot"><span>2026 season to date</span><time dateTime={report.as_of}>Snapshot {calendarDate(report.as_of, true)}</time><div className="md-season-downloads"><a className="md-text-link" href={SEASON_REPORT_PATH} download>Report JSON <Download size={14} /></a><a className="md-text-link" href={SEASON_DECISIONS_PATH} download>Audit rows CSV <Download size={14} /></a></div></div>}
    </div>
    {query.isLoading ? <div className="md-season-loading" role="status"><p>Reading the season record…</p><div /><div /><div /></div>
      : query.isError || !report ? <div className="md-board-empty" role="alert"><h2>The season report is unavailable.</h2><p>Try again, or open Current store for the available database record.</p><button className="md-button" onClick={() => void query.refetch()} disabled={query.isFetching}>Try again</button></div>
      : <>
        <div className="md-season-basis"><Info size={18} /><p><strong>Stored paper records.</strong> Returns describe complete, consistent contracts. Incomplete and conflicting groups stay visible but are excluded from performance. These are not verified placed bets or bankroll returns.</p></div>
        <div className="md-season-market-heading">
          <div><h2>Market record</h2><p>Returns use complete, consistent contracts. Select a market to inspect coverage.</p></div>
          <div className="md-mode" role="group" aria-label="Historical model lane">{[{ key: "dashboard", label: "Dashboard" }, { key: "lab", label: "Lab" }].map(item => <button key={item.key} aria-pressed={lane === item.key} onClick={() => setLane(item.key)}>{item.label}</button>)}</div>
        </div>
        {report.markets.length ? <div className="md-results-table-wrap md-season-table-wrap">
          <table className="md-results-table md-season-markets-table">
            <caption className="md-sr-only">{lane === "dashboard" ? "Dashboard" : "Lab"} model market record. Return metrics include only complete, consistent contracts.</caption>
            <thead><tr><th>Market</th><th>All records</th><th>Win / loss</th><th>Qualified zero /<br />stored void</th><th>Incomplete / conflict</th><th>Paper return</th><th>Selection eligible</th></tr></thead>
            <tbody>{report.markets.map(item => {
              const values = item.lanes.find(value => value.lane === lane)
              return <tr key={item.key} className={`${market === item.key ? "is-selected" : ""} ${!values?.records ? "is-empty" : ""}`}>
                <th scope="row"><button className="md-season-market-button" aria-pressed={market === item.key} onClick={() => setMarket(current => current === item.key ? null : item.key)}>{item.label}</button><small>{values?.records ? `${count(values.events)} events` : "No records in this lane"}</small>
                  {(values?.missing_round || 0) > 0 && <small className="md-season-market-note">{count(values?.missing_round)} missing round IDs; those returns withheld.</small>}
                  {!!values?.records && <details className="md-season-mobile-details"><summary>Outcome &amp; evidence details <ChevronDown size={14} /></summary><dl>
                    <div><dt>Win / loss</dt><dd>{count(values.wins)} wins · {count(values.losses)} losses</dd></div>
                    <div><dt>Qualified zero returns</dt><dd>{count(values.zero_return)}</dd></div>
                    <div><dt>Stored voids</dt><dd>{count(values.void)}</dd></div>
                    <div><dt>Incomplete / conflicting</dt><dd>{count(values.incomplete)} incomplete · {count(values.conflicts)} conflicting</dd></div>
                    <div><dt>Ungraded</dt><dd>{count(values.ungraded)}</dd></div>
                    <div><dt>Selection eligible</dt><dd>{count(values.selection_eligible)}</dd></div>
                  </dl></details>}
                </th>
                <td className="md-season-mobile-primary" data-label="All records">{count(values?.records)}<small className="md-season-ungraded">{count(values?.ungraded)} ungraded</small></td>
                <td className="md-season-secondary" data-label="Win / loss">{count(values?.wins)} / {count(values?.losses)}</td>
                <td className="md-season-secondary" data-label="Qualified zero / stored void">{count(values?.zero_return)} / {count(values?.void)}</td>
                <td className="md-season-secondary" data-label="Incomplete / conflict">{count(values?.incomplete)} / {count(values?.conflicts)}</td>
                <td className="md-season-mobile-primary" data-label="Paper return"><span className={typeof values?.profit === "number" && values.profit > 0 ? "md-positive" : ""}>{units(values?.profit)}</span><small>{percent(values?.roi)} ROI · {count(values?.settled)} settled</small></td>
                <td className="md-season-secondary" data-label="Selection eligible">{count(values?.selection_eligible)}</td>
              </tr>
            })}</tbody>
          </table>
        </div> : <div className="md-board-empty"><h2>No reconciled market records yet.</h2><p>Missing history is not counted as a loss.</p></div>}
        <p className="md-season-table-note">ROI = stored profit ÷ stored stake for complete, consistent settled records. Stored consistency is not independent sportsbook settlement verification. Qualified zero returns are not assumed pushes; stored voids are archive labels. Incomplete and conflict counts can overlap. Selection eligibility also requires usable pre-event timing and price evidence.</p>
        <EventCoverage report={report} market={market} onMarketChange={setMarket} />
        <section className="md-season-selection" aria-labelledby="season-selection-title">
          <div><h2 id="season-selection-title">What can guide the next card?</h2><p><strong>No rule promoted</strong>. {selectionMessage}</p></div>
          <div><p><strong>Report-wide:</strong> {count(report.coverage.selection_eligible)} eligible records across all markets, model lanes and versions. Model outputs remain unchanged.</p></div>
          <div className="md-season-rule-results">
            <div className="md-season-rule-heading">
              <h3>{researchLabel} · {lane === "dashboard" ? "Dashboard" : "Lab"}{variant ? ` · ${variantLabel(variant)}` : ""}</h3>
              <div className="md-season-rule-controls"><MarketSelect report={report} market={researchMarket} onChange={setMarket} label="Selection research market" allowAll={false} />{variants.length > 0 && <label className="md-select"><span>Model version</span><select aria-label="Selection research model version" value={variant} onChange={event => setPreferredVariant(event.target.value)}>{variants.map(value => <option key={value} value={value}>{variantLabel(value)}</option>)}</select></label>}</div>
            </div>
            {rules.length ? <>
              <p className="md-season-scope-count"><strong>Selected scope:</strong> {count(scopeBaseline?.eligible_decisions)} eligible records across {count(scopeBaseline?.eligible_events)} events. Requires at least {count(report.selection.minimum_earlier_events)} earlier events, {count(report.selection.minimum_later_events)} later events and {count(report.selection.minimum_later_decisions)} later decisions.</p>
              <details key={`${lane}:${researchMarket}:${variant}`} className="md-season-details md-season-rule-disclosure" open={rules.some(rule => rule.sufficient)}>
                <summary>Inspect {rules.length} fixed {rules.length === 1 ? "rule" : "rules"} <ChevronDown size={16} /></summary>
              <div className="md-season-table-wrap">
                <table className="md-season-rule-table">
                  <caption className="md-sr-only">Fixed selection rules compared across an earlier and later retrospective event split</caption>
                  <thead><tr><th>Fixed rule</th><th>Earlier / later events</th><th>Later decisions</th><th>Later paper ROI</th></tr></thead>
                  <tbody>{rules.map(rule => <tr key={`${rule.id}:${rule.lane}:${rule.market}:${rule.model_variant}`}>
                    <th scope="row">{rule.label}</th>
                    <td data-label="Earlier / later events">{count(rule.earlier_events)} / {count(rule.later_events)}</td>
                    <td data-label="Later decisions">{count(rule.later_decisions)}</td>
                    <td data-label="Later paper ROI">{percent(rule.later_roi)}<small>{rule.roi_interval ? `${percent(rule.roi_interval[0])} to ${percent(rule.roi_interval[1])}` : "Interval unavailable"}</small></td>
                  </tr>)}</tbody>
                </table>
              </div>
              <p>Later events are a retrospective comparison, not an untouched holdout. Intervals reflect event-level uncertainty. No rule here changes the live pick order.</p>
              </details>
            </> : <p>No rule comparison is available for this market and model lane.</p>}
          </div>
        </section>
        <details className="md-season-details">
          <summary>Sources, gaps &amp; reading the record <ChevronDown size={16} /></summary>
          <div className="md-season-audit">
            <dl>
              <div><dt>Source generations</dt><dd>{count(report.coverage.source_generations)}</dd></div>
              <div><dt>Original pick observations</dt><dd>{count(report.coverage.pick_observations)}</dd></div>
              <div><dt>Reconciled decision groups</dt><dd>{count(report.coverage.decision_groups)}</dd></div>
              <div><dt>Unresolved event identities</dt><dd>{count(report.coverage.unresolved_events)}</dd></div>
              <div><dt>Unreadable sources</dt><dd>{count(report.coverage.unreadable_sources)}</dd></div>
              <div><dt>Salvaged observations</dt><dd>{count(report.coverage.salvaged_observations)}</dd></div>
            </dl>
            {report.issues.length > 0 && <ul className="md-season-issues">{report.issues.map(issue => <li key={issue.key}><span>{issue.label}</span><strong>{count(issue.count)}</strong></li>)}</ul>}
          </div>
          {report.caveats.map((caveat, index) => <p key={index}>{caveat}</p>)}
          <p className="md-season-report-id">Report {report.provenance.report_id}. Source and calendar hashes are included in the downloadable report.</p>
        </details>
      </>}
  </section>
}
