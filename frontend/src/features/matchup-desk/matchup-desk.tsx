import { lazy, Suspense, useEffect, useMemo, useState } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { Link, NavLink, useLocation, useSearchParams } from "react-router-dom"
import {
  ArrowDown,
  ArrowRight,
  Check,
  ChevronDown,
  Clock3,
  Flag,
  Info,
  Plus,
  RefreshCw,
  Search,
} from "lucide-react"
import { ThemeToggle } from "@/components/theme-toggle"
import {
  getDeskBoard,
  getReadOnlyJson,
  type OperatorBoard,
  type OperatorMode,
} from "@/features/operator-data/operator-api"
import {
  boardRows,
  CARD_KEY,
  formatEdge,
  formatPrice,
  formatProbability,
  MARKET_LABELS,
  readSavedCard,
  type DeskRow,
  type MarketFamily,
  type SavedPick,
} from "./market-rows"
import { CardPage } from "./card-page"
import "./matchup-desk.css"
import "./season-results.css"

const SeasonResults = lazy(() => import("./season-results").then(module => ({ default: module.SeasonResults })))

type Calibration = {
  n: number
  brier: number | null
  bins: Array<{ n: number; mean_probability: number; observed_rate: number }>
  note?: string
}
type EvidenceMarket = {
  calibration?: Calibration
  limitations?: string[]
  low_sample?: boolean
  key: string
  label?: string
  records?: number
  graded?: number
  wins?: number
  losses?: number
  pushes?: number
  voids?: number
  unknown?: number
  ungraded?: number
  event_count?: number
  net_units?: number | null
  flat_unit_roi_pct?: number | null
  profit_covered_records?: number
  [key: string]: unknown
}
type Evidence = {
  state: string
  generated_at?: string
  coverage?: Record<string, unknown>
  markets?: EvidenceMarket[]
  caveats?: string[]
  gaps?: unknown[]
  [key: string]: unknown
}
const text = (value: unknown, fallback = "—") =>
  value === null || value === undefined || value === ""
    ? fallback
    : String(value)
const date = (value: string | null | undefined) => {
  if (!value) return "Time unavailable"
  const d = new Date(value)
  return Number.isNaN(d.getTime())
    ? "Time unavailable"
    : new Intl.DateTimeFormat(undefined, {
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
      }).format(d)
}
const bookName = (v: string) =>
  ({
    draftkings: "DraftKings",
    fanduel: "FanDuel",
    bovada: "Bovada",
    skybet: "Sky Bet",
    betmgm: "BetMGM",
    pinnacle: "Pinnacle",
  })[v.toLowerCase()] ||
  v ||
  "Book unavailable"
function getEvidence(signal?: AbortSignal): Promise<Evidence> {
  return getReadOnlyJson<Evidence>("/api/market-evidence?lane=dashboard", signal)
}

function EvidenceAside({
  evidence,
  error,
}: {
  evidence?: Evidence
  error: boolean
}) {
  return (
    <aside className="md-evidence-aside" aria-label="Market evidence">
      <div className="md-aside-heading">
        <h2>Market record</h2>
        <ArrowRight size={19} />
      </div>
      {error || evidence?.state === "unavailable" ? (
        <p className="md-muted">
          Historical evidence is temporarily unavailable.
        </p>
      ) : evidence ? (
        <>
          <p>
            {text(evidence.coverage?.event_count)} events in the available
            record. Season history is still being reconciled.
          </p>
          <div className="md-market-records">
            {(evidence.markets || [])
              .filter((m) => m.key !== "other")
              .map((m) => (
                <Link key={m.key} to="/evidence">
                  <strong>
                    {MARKET_LABELS[m.key as MarketFamily] || m.label}
                  </strong>
                  <span>
                    {text(m.wins, "0")} W · {text(m.losses, "0")} L
                  </span>
                  <small>
                    {text(m.event_count, "0")} events ·{" "}
                    {m.low_sample ? "Limited sample" : "View evidence"}
                  </small>
                </Link>
              ))}
          </div>
        </>
      ) : (
        <p className="md-muted">Loading the available record…</p>
      )}
      <Link className="md-text-link" to="/evidence">
        Explore market results <ArrowRight size={16} />
      </Link>
      <p className="md-record-caveat">
        Model selections, not verified placed bets. Pushes, voids and unresolved
        selections are separated in Results.
      </p>
    </aside>
  )
}

function CalibrationChart({ markets }: { markets: EvidenceMarket[] }) {
  const [key, setKey] = useState("72h")
  const market = markets.find((m) => m.key === key)
  const calibration = market?.calibration
  return (
    <section className="md-calibration">
      <div className="md-subsection-heading">
        <h2>Forecast vs. outcome</h2>
        <label className="md-select">
          <select
            aria-label="Calibration market"
            value={key}
            onChange={(e) => setKey(e.target.value)}
          >
            {markets
              .filter((m) => m.key !== "other")
              .map((m) => (
                <option key={m.key} value={m.key}>
                  {m.label || m.key}
                </option>
              ))}
          </select>
        </label>
      </div>
      <div className="md-calibration-layout">
        <div>
          {calibration?.bins.length ? (
            <svg
              className="md-calibration-plot"
              viewBox="0 0 520 300"
              role="img"
              aria-label={`${market?.label}: predicted probability against actual win rate, ${calibration.n} settled win or loss records`}
            >
              {[0, 0.25, 0.5, 0.75, 1].map((n) => (
                <g key={n}>
                  <line
                    x1="52"
                    x2="488"
                    y1={254 - n * 222}
                    y2={254 - n * 222}
                    className="md-plot-grid"
                  />
                  <text x="42" y={258 - n * 222} textAnchor="end">
                    {n * 100}%
                  </text>
                  <text x={52 + n * 436} y="274" textAnchor="middle">
                    {n * 100}%
                  </text>
                </g>
              ))}
              <line
                x1="52"
                y1="254"
                x2="488"
                y2="32"
                className="md-plot-reference"
              />
              {calibration.bins.map((bin, i) => (
                <circle
                  key={i}
                  cx={52 + bin.mean_probability * 436}
                  cy={254 - bin.observed_rate * 222}
                  r={5 + Math.min(7, Math.sqrt(bin.n))}
                  className="md-plot-point"
                >
                  <title>
                    {formatProbability(bin.mean_probability)} predicted ·{" "}
                    {formatProbability(bin.observed_rate)} observed · {bin.n}{" "}
                    results
                  </title>
                </circle>
              ))}
              <text x="270" y="297" textAnchor="middle">
                Model win probability
              </text>
              <text x="52" y="17">
                Observed win rate
              </text>
            </svg>
          ) : (
            <div className="md-calibration-empty">
              No comparable settled results for this market.
            </div>
          )}
        </div>
        <div className="md-calibration-notes">
          <p>
            The diagonal marks a match between the forecast and the observed win
            rate. Larger points contain more results.
          </p>
          <dl>
            <div>
              <dt>Comparable results</dt>
              <dd>{calibration?.n ?? 0}</dd>
            </div>
            <div>
              <dt>Forecast error (Brier)</dt>
              <dd>
                {typeof calibration?.brier === "number"
                  ? calibration.brier.toFixed(3)
                  : "—"}
              </dd>
            </div>
          </dl>
          <p>
            Lower Brier scores indicate less forecast error. Compare the same
            market over time.
          </p>
          {market?.low_sample && (
            <p className="md-sample-warning">
              Limited sample. This record does not establish a repeatable edge.
            </p>
          )}
          <p>{calibration?.note}</p>
        </div>
      </div>
    </section>
  )
}

function MatchupRow({
  row,
  saved,
  checking,
  onSave,
}: {
  row: DeskRow
  saved: boolean
  checking: boolean
  onSave: (row: DeskRow) => void
}) {
  const [open, setOpen] = useState(false)
  return (
    <div className={`md-matchup${open ? " is-open" : ""}`}>
      <div className="md-matchup-line">
        <button
          className="md-pair-button"
          onClick={() => setOpen(!open)}
          aria-expanded={open}
        >
          <span className="md-player">{row.player}</span>
          <span className="md-opponent">
            {row.opponent
              ? `vs ${row.opponent}`
              : row.marketType.replaceAll("_", " ")}
            {row.round ? ` · R${row.round}` : ""}
          </span>
          <ChevronDown className="md-row-chevron" size={16} />
        </button>
        <div className="md-price">
          <span className="md-mobile-label">Price</span>
          <strong>{formatPrice(row.odds)}</strong>
          <span>{bookName(row.book)}</span>
        </div>
        <div className="md-number">
          <span className="md-mobile-label">Model</span>
          {formatProbability(row.probability)}
        </div>
        <div
          className={`md-number ${row.ev !== null && row.ev > 0 ? "md-positive" : ""}`}
        >
          <span className="md-mobile-label">Model EV</span>
          {formatEdge(row.ev)}
        </div>
        <button
          className={`md-save${saved ? " is-saved" : ""}`}
          disabled={(!row.eligible || checking) && !saved}
          title={
            checking && !saved
              ? "Checking the latest published quote"
              : !row.eligible
              ? "This quote is not eligible for the betting card"
              : saved
                ? "Saved to your card"
                : "Save this quote"
          }
          aria-label={
            saved ? `${row.player} saved to card` : `Save ${row.player} to card`
          }
          onClick={() => onSave(row)}
        >
          {saved ? <Check size={18} /> : <Plus size={18} />}
        </button>
      </div>
      {open && (
        <div className="md-matchup-detail">
          {row.probability !== null && row.impliedProbability != null ? (
            <div className="md-duel">
              <div>
                <strong className="md-model-legend">
                  Model win probability
                </strong>
                <span>{formatProbability(row.probability)}</span>
              </div>
              <div
                className="md-duel-rule"
                role="img"
                aria-label={`Model ${formatProbability(row.probability)}; book break-even ${formatProbability(row.impliedProbability ?? null)} on a shared probability scale`}
              >
                <span
                  className="md-model-mark"
                  style={{ left: `${row.probability * 100}%` }}
                />
                <span
                  className="md-book-mark"
                  style={{ left: `${(row.impliedProbability ?? 0) * 100}%` }}
                />
              </div>
              <div>
                <span>{formatProbability(row.impliedProbability ?? null)}</span>
                <strong className="md-book-legend">Book break-even</strong>
              </div>
            </div>
          ) : null}
          <p>
            {row.reason ||
              "No additional model explanation was included with this quote."}
          </p>
          <div className="md-detail-foot">
            <span>Quote time: {date(row.lineAt)}</span>
            <span>Snapshot: {date(row.snapshotAt)}</span>
            <span>{row.marketType.replaceAll("_", " ")}</span>
          </div>
          {!row.eligible && (
            <p className="md-muted">
              Research view only. This row is stale, in play, incomplete or
              withheld by its source.
            </p>
          )}
        </div>
      )}
    </div>
  )
}

function MarketBoard({
  board,
  loading,
  checking,
  error,
  refresh,
  evidence,
  evidenceError,
  savedCard,
  save,
}: {
  board?: OperatorBoard
  loading: boolean
  checking: boolean
  error: boolean
  refresh: () => void
  evidence?: Evidence
  evidenceError: boolean
  savedCard: SavedPick[]
  save: (row: DeskRow) => void
}) {
  const [params, setParams] = useSearchParams()
  const market = (
    ["72h", "18h", "group", "other"].includes(params.get("market") || "")
      ? params.get("market")
      : "72h"
  ) as MarketFamily
  const search = params.get("q") || ""
  const book = params.get("book") || ""
  const minEdge = [2, 3, 5, 8, 10].includes(Number(params.get("ev"))) ? Number(params.get("ev")) : 0
  const sort = params.get("sort") === "player" ? "player" : "edge"
  function updateFilter(key: string, value: string) {
    setParams(previous => {
      const next = new URLSearchParams(previous)
      if (value) next.set(key, value)
      else next.delete(key)
      return next
    }, { replace: true })
  }
  const rows = useMemo(() => boardRows(board), [board])
  const marketRows = rows.filter((row) => row.market === market)
  const books = [
    ...new Set(marketRows.map((row) => row.book).filter(Boolean)),
  ].sort()
  const filtered = marketRows
    .filter(
      (row) =>
        (!search ||
          `${row.player} ${row.opponent}`
            .toLowerCase()
            .includes(search.toLowerCase())) &&
        (!book || row.book === book) &&
        (minEdge === 0 || (row.ev !== null && row.ev >= minEdge / 100))
    )
    .sort((a, b) =>
      sort === "edge"
        ? (b.ev ?? -Infinity) - (a.ev ?? -Infinity)
        : a.player.localeCompare(b.player)
    )
  const activeFilters = !!search || !!book || minEdge !== 0
  const savedIds = new Set(savedCard.map((row) => row.id))
  const unavailable = board?.state === "unavailable" || board?.state === "error"
  function switchMarket(next: MarketFamily) {
    const p = new URLSearchParams(params)
    p.set("market", next)
    p.delete("book")
    setParams(p)
  }
  return (
    <div className="md-board-layout">
      <section className="md-market-section" aria-label="Market board">
        <div className="md-section-title">
          <div>
            <h1>Find your matchups.</h1>
            <p>The price, the model, and the case for each side.</p>
          </div>
          <span className="md-total">
            {loading
              ? "Loading"
              : `${rows.length} ${rows.length === 1 ? "quote" : "quotes"}`}
          </span>
        </div>
        <div
          className="md-market-tabs"
          role="group"
          aria-label="Market duration"
        >
          {(Object.keys(MARKET_LABELS) as MarketFamily[]).map((key) => (
            <button
              key={key}
              aria-pressed={market === key}
              onClick={() => switchMarket(key)}
            >
              {MARKET_LABELS[key]}
              <span>{rows.filter((row) => row.market === key).length}</span>
            </button>
          ))}
        </div>
        <div className="md-filters">
          <label className="md-search">
            <Search size={17} />
            <input
              value={search}
              onChange={(e) => updateFilter("q", e.target.value)}
              placeholder="Find a player or matchup"
              aria-label="Find a player or matchup"
            />
          </label>
          <label className="md-select">
            <span>Book</span>
            <select
              aria-label="Sportsbook"
              value={book}
              onChange={(e) => updateFilter("book", e.target.value)}
            >
              <option value="">All books</option>
              {books.map((b) => (
                <option key={b} value={b}>
                  {bookName(b)}
                </option>
              ))}
            </select>
          </label>
          <label className="md-select">
            <span>Min. EV</span>
            <select
              value={minEdge}
              onChange={(e) => updateFilter("ev", e.target.value === "0" ? "" : e.target.value)}
              aria-label="Minimum model EV"
            >
              {[0, 2, 3, 5, 8, 10].map((n) => (
                <option key={n} value={n}>
                  {n === 0 ? "Any" : `${n}%`}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="md-table-head">
          <button
            onClick={() => updateFilter("sort", sort === "player" ? "" : "player")}
          >
            Matchup {sort === "player" && <ArrowDown size={12} />}
          </button>
          <span>Book price</span>
          <span>Model win</span>
          <button onClick={() => updateFilter("sort", "")}>
            Model EV {sort === "edge" && <ArrowDown size={12} />}
          </button>
          <span>Card</span>
        </div>
        {loading ? (
          <div className="md-board-empty" role="status">
            <RefreshCw size={30} />
            <h2>Reading the market.</h2>
            <p>Loading the latest published predictions and prices.</p>
          </div>
        ) : error ? (
          <div className="md-board-empty" role="alert">
            <Info size={30} />
            <h2>The board couldn’t load.</h2>
            <p>
              Your saved card is still available. Try loading the board again.
            </p>
            <button className="md-button" onClick={refresh}>
              Try again
            </button>
          </div>
        ) : unavailable ? (
          <div className="md-board-empty">
            <Info size={30} />
            <h2>This event needs verification.</h2>
            <p>
              {board?.reason.message ||
                "A verified event snapshot is not available."}
            </p>
            <Link to="/system" className="md-text-link">
              View data status <ArrowRight size={16} />
            </Link>
          </div>
        ) : filtered.length ? (
          <div className="md-matchup-list">
            {filtered.map((row) => (
              <MatchupRow
                key={row.id}
                row={row}
                checking={checking}
                saved={savedIds.has(row.id)}
                onSave={save}
              />
            ))}
          </div>
        ) : (
          <div className="md-board-empty">
            <Flag size={32} />
            <h2>
              {activeFilters
                ? "No matchups fit these filters."
                : market === "group"
                  ? "No eligible group prices yet."
                  : market === "other"
                    ? "No other markets published."
                    : "Waiting for the market."}
            </h2>
            <p>
              {activeFilters
                ? "Widen your search or lower the EV threshold to see more of the board."
                : market === "group"
                  ? "Group markets will appear here when the existing model publishes eligible priced selections. Shadow projections stay in research."
                  : "There are no published quotes for this market in the selected event. The field is available for research while prices develop."}
            </p>
            {activeFilters ? (
              <button
                className="md-button"
                onClick={() => {
                  const next = new URLSearchParams(params)
                  for (const key of ["q", "book", "ev"]) next.delete(key)
                  setParams(next, { replace: true })
                }}
              >
                Clear filters
              </button>
            ) : (
              <Link className="md-text-link" to="/players">
                Research the field <ArrowRight size={16} />
              </Link>
            )}
          </div>
        )}
        <div className="md-board-foot">
          <span>
            {filtered.length} displayed · {MARKET_LABELS[market]}
          </span>
          <span>Prices can move. Check the book before placing a bet.</span>
        </div>
        {board && board.rankings.length > 0 && (
          <div className="md-field-preview">
            <div className="md-subsection-heading">
              <h2>Inside the field</h2>
              <Link to="/players">
                All {board.rankings.length} players <ArrowRight size={14} />
              </Link>
            </div>
            <div className="md-field-list">
              {board.rankings.slice(0, 5).map((row, i) => (
                <Link
                  key={text(row.player_key, i.toString())}
                  to={`/players/${encodeURIComponent(text(row.player_key || row.player, ""))}`}
                >
                  <span className="md-rank">{i + 1}</span>
                  <span>
                    {text(
                      row.player ||
                        row.player_display ||
                        row.name ||
                        row.player_key
                    )}
                  </span>
                  <span className="md-field-score">
                    {typeof row.composite === "number"
                      ? row.composite.toFixed(1)
                      : typeof row.composite_score === "number"
                        ? row.composite_score.toFixed(1)
                        : "—"}
                  </span>
                </Link>
              ))}
            </div>
            <p className="md-muted">
              Model ranking · supplied by the selected event snapshot
            </p>
          </div>
        )}
      </section>
      <EvidenceAside evidence={evidence} error={evidenceError} />
    </div>
  )
}

function ResultsPage({
  evidence,
  loading,
  error,
  retry,
}: {
  evidence?: Evidence
  loading: boolean
  error: boolean
  retry: () => void
}) {
  const markets = evidence?.markets || []
  return (
    <section className="md-single-page">
      <div className="md-section-title">
        <div>
          <h1>Know where the edge holds.</h1>
          <p>
            The available record, split by market. Original predictions and
            settled outcomes.
          </p>
        </div>
        <Link className="md-text-link" to="/results">
          Event archive <ArrowRight size={16} />
        </Link>
      </div>
      <div className="md-evidence-banner">
        <Info size={19} />
        <div>
          <strong>Available history, not a complete season.</strong>
          <p>
            Historical recovery is still being reconciled. These records
            describe model selections, not verified placed bets. Flat-stake ROI
            normalizes each recorded return to a one-unit stake. It is not your
            bankroll return.
          </p>
        </div>
      </div>
      {loading ? (
        <div className="md-board-empty" role="status">
          <h2>Reading the results…</h2>
        </div>
      ) : error || evidence?.state === "unavailable" ? (
        <div className="md-board-empty" role="alert">
          <h2>Evidence is unavailable.</h2>
          <p>The original event archive is still accessible.</p>
          <button className="md-button" onClick={retry}>
            Try again
          </button>
        </div>
      ) : (
        <>
          <div className="md-results-summary">
            <span>
              <strong>{text(evidence?.coverage?.event_count)}</strong> events
            </span>
            <span>
              <strong>{text(evidence?.coverage?.record_count)}</strong>{" "}
              selections
            </span>
            <span>
              {text(evidence?.coverage?.conflicting_identities, "0")}{" "}
              conflicting identities excluded · Dashboard model only
            </span>
          </div>
          <div className="md-results-table-wrap">
            <table className="md-results-table">
              <thead>
                <tr>
                  <th>Market</th>
                  <th>Graded</th>
                  <th>Win / loss</th>
                  <th>Push / void</th>
                  <th>Unresolved</th>
                  <th>Recorded P&amp;L</th>
                  <th>Flat-stake ROI</th>
                </tr>
              </thead>
              <tbody>
                {markets.map((m, i) => (
                  <tr key={`${m.key}-${i}`}>
                    <th scope="row">
                      {m.label || m.key}
                      <small>{text(m.event_count, "0")} events</small>
                    </th>
                    <td data-label="Graded">{text(m.graded)}</td>
                    <td data-label="Win / loss">
                      {text(m.wins, "0")} / {text(m.losses, "0")}
                    </td>
                    <td data-label="Push / void">
                      {text(m.pushes, "0")} / {text(m.voids, "0")}
                    </td>
                    <td data-label="Unresolved">
                      {(m.ungraded || 0) + (m.unknown || 0)}
                    </td>
                    <td
                      data-label="Recorded P&L"
                      className={
                        typeof m.net_units === "number" && m.net_units > 0
                          ? "md-positive"
                          : ""
                      }
                    >
                      {typeof m.net_units === "number"
                        ? `${m.net_units > 0 ? "+" : ""}${m.net_units.toFixed(2)}u`
                        : "—"}
                      <small>
                        {text(m.profit_covered_records, "0")} records with P&L
                        data
                      </small>
                    </td>
                    <td data-label="Flat-stake ROI">
                      {typeof m.flat_unit_roi_pct === "number"
                        ? `${m.flat_unit_roi_pct.toFixed(1)}%`
                        : "Unavailable"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!markets.length && (
            <div className="md-board-empty">
              <h2>No settled market evidence yet.</h2>
              <p>Missing results are kept separate from losses.</p>
            </div>
          )}
        </>
      )}
      {markets.length > 0 && <CalibrationChart markets={markets} />}
      {evidence?.caveats?.length ? (
        <details className="md-evidence-details">
          <summary>
            How to read this record <ChevronDown size={16} />
          </summary>
          {evidence.caveats.map((c, i) => (
            <p key={i}>{c}</p>
          ))}
        </details>
      ) : null}
    </section>
  )
}

export function MatchupDesk() {
  const queryClient = useQueryClient()
  const location = useLocation()
  const [params, setParams] = useSearchParams()
  const mode: OperatorMode = params.get("mode") === "live" ? "live" : "upcoming"
  const [card, setCard] = useState<SavedPick[]>(readSavedCard)
  const [storageError, setStorageError] = useState(false)
  const [notice, setNotice] = useState("")
  const boardPage = location.pathname !== "/card" && location.pathname !== "/evidence"
  const evidencePage = location.pathname === "/evidence"
  const currentStoreView = evidencePage && params.get("view") === "store"
  const needsCurrentEvidence = boardPage || currentStoreView
  const boardQuery = useQuery({
    queryKey: ["matchup-desk", mode],
    queryFn: ({ signal }) => getDeskBoard({ track: "champion", mode }, signal),
    enabled: boardPage,
    staleTime: 30_000,
    refetchInterval: boardPage ? 60_000 : false,
    retry: false,
  })
  const evidenceQuery = useQuery({
    queryKey: ["market-evidence", "dashboard"],
    queryFn: ({ signal }) => getEvidence(signal),
    enabled: needsCurrentEvidence,
    staleTime: 60_000,
    refetchInterval: needsCurrentEvidence ? 300_000 : false,
    retry: false,
  })
  const board = boardQuery.data
  useEffect(() => {
    if (!boardPage) void queryClient.cancelQueries({ queryKey: ["matchup-desk"] })
    if (!needsCurrentEvidence) void queryClient.cancelQueries({ queryKey: ["market-evidence", "dashboard"] })
  }, [boardPage, needsCurrentEvidence, queryClient])
  useEffect(() => {
    document.title = `${location.pathname === "/card" ? "My card" : location.pathname === "/evidence" ? "Market results" : "Matchups"} · Golf Model`
  }, [location.pathname])
  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key === CARD_KEY) setCard(readSavedCard())
    }
    window.addEventListener("storage", onStorage)
    return () => window.removeEventListener("storage", onStorage)
  }, [])
  function persist(next: SavedPick[]) {
    try {
      localStorage.setItem(CARD_KEY, JSON.stringify(next))
      setCard(next)
      setStorageError(false)
      return true
    } catch {
      setStorageError(true)
      return false
    }
  }
  function save(row: DeskRow) {
    if (boardQuery.isFetching || boardQuery.isError || !row.eligible || card.some((p) => p.id === row.id)) return
    if (persist([...card, { ...row, savedAt: new Date().toISOString() }]))
      setNotice(`${row.player} saved to your card`)
  }
  const age = board?.source.age_seconds
  const sourceLabel = boardQuery.isError
    ? "Connection unavailable"
    : boardQuery.isFetching && board
      ? "Checking latest quotes…"
    : !board
      ? "Loading data"
      : board.state === "stale"
        ? "Stale snapshot"
        : board.state === "unavailable"
          ? "Verification needed"
          : board.state === "error"
            ? "Data error"
            : typeof age === "number"
              ? `Updated ${age < 60 ? "just now" : `${Math.floor(age / 60)}m ago`}`
              : "Timestamp unavailable"
  return (
    <div className="matchup-desk">
      <a className="md-skip" href="#desk-main">
        Skip to content
      </a>
      <header className="md-masthead">
        <Link className="md-brand" to="/" aria-label="Golf Model home">
          <Flag size={24} />
          <span>
            GOLF<span>MODEL</span>
          </span>
        </Link>
        <nav aria-label="Main navigation">
          <NavLink to={`/${location.search}`} end>
            Markets
          </NavLink>
          <NavLink to={`/card${location.search}`}>
            My card<span className="md-card-count">{card.length}</span>
          </NavLink>
          <NavLink to={`/evidence${location.search}`}>Results</NavLink>
        </nav>
        <div className="md-header-tools">
          <details className="md-more">
            <summary>
              More tools <ChevronDown size={14} />
            </summary>
            <div>
              <Link to="/compare/players">Compare players</Link>
              <Link to="/players">Player research</Link>
              <Link to="/results">Event archive</Link>
              <Link to="/lab">Model lab</Link>
              <Link to="/system">System status</Link>
            </div>
          </details>
          <ThemeToggle />
        </div>
      </header>
      {boardPage && <div className="md-event-bar">
        <div className="md-event-name">
          <span className="md-tour">PGA TOUR</span>
          <h2>
            {board?.event.event_name ||
              (boardQuery.isLoading ? "Loading event…" : "Event unavailable")}
          </h2>
          <p>
            {board?.event.course_name || "Awaiting verified course"}
            {board?.rankings.length
              ? ` · ${board.rankings.length} players`
              : ""}
          </p>
        </div>
        <div className="md-event-actions">
          {boardPage && (
            <div className="md-mode" role="group" aria-label="Event context">
              {(["upcoming", "live"] as const).map((v) => (
                <button
                  key={v}
                  aria-pressed={mode === v}
                  onClick={() => {
                    const p = new URLSearchParams(params)
                    p.set("mode", v)
                    setParams(p)
                  }}
                >
                  {v === "upcoming" ? "Upcoming" : "In play"}
                </button>
              ))}
            </div>
          )}
          <div className="md-freshness">
            <span
              className={`md-data-state ${boardQuery.isError || board?.state === "stale" || board?.state === "unavailable" ? "is-warning" : ""}`}
            >
              {sourceLabel}
            </span>
            <button
              aria-label="Reload published data"
              title="Reload published data"
              disabled={boardQuery.isFetching}
              onClick={() => {
                void boardQuery.refetch()
                void evidenceQuery.refetch()
              }}
            >
              <RefreshCw size={15} />
            </button>
          </div>
        </div>
      </div>}
      {board?.state === "stale" && boardPage && (
        <div className="md-stale-warning" role="status">
          <Clock3 size={16} />
          Published data is older than its freshness window. Saving quotes is
          paused until a fresh snapshot arrives.
        </div>
      )}
      {storageError && (
        <div className="md-stale-warning" role="alert">
          Your browser couldn’t save this card. Enable local storage and try
          again.
        </div>
      )}
      <main id="desk-main" className="md-main">
        {location.pathname === "/card" ? (
          <CardPage
            card={card}
            remove={(id) => persist(card.filter((r) => r.id !== id))}
            marketSearch={location.search}
          />
        ) : location.pathname === "/evidence" ? (
          <>
            <nav className="md-results-view-switch" aria-label="Results view">
              {[{ key: "season", label: "Season record" }, { key: "store", label: "Current store" }].map(view => {
                const next = new URLSearchParams(params)
                if (view.key === "store") next.set("view", "store")
                else next.delete("view")
                const selected = view.key === "store" ? currentStoreView : !currentStoreView
                return <Link key={view.key} to={{ pathname: "/evidence", search: next.toString() }} aria-current={selected ? "page" : undefined}>{view.label}</Link>
              })}
            </nav>
            {currentStoreView ? <ResultsPage
              evidence={evidenceQuery.data}
              loading={evidenceQuery.isLoading}
              error={evidenceQuery.isError || evidenceQuery.data?.state === "unavailable"}
              retry={() => void evidenceQuery.refetch()}
            /> : <Suspense fallback={<div className="md-single-page md-season-loading" role="status">Opening the season record…</div>}><SeasonResults /></Suspense>}
          </>
        ) : (
          <MarketBoard
            board={board}
            loading={boardQuery.isLoading}
            checking={boardQuery.isFetching}
            error={boardQuery.isError}
            refresh={() => void boardQuery.refetch()}
            evidence={evidenceQuery.data}
            evidenceError={evidenceQuery.isError}
            savedCard={card}
            save={save}
          />
        )}
      </main>
      <footer className="md-footer">
        <span>Golf Model</span>
        <span>Original model outputs. Clearer decisions.</span>
        <Link to="/system">
          Data &amp; system status <ArrowRight size={13} />
        </Link>
      </footer>
      <div className="md-sr-only" role="status" aria-live="polite">
        {notice}
      </div>
    </div>
  )
}
