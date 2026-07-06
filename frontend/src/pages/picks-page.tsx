/**
 * Picks Page
 *
 * Unified pre-tournament picks view, mirroring the Players page pattern:
 * - Matchups sub-tab: head-to-head value bets with tier badges and EV
 * - Secondary sub-tab: top-finish / make-cut / outright edges with confidence tiers
 *
 * Route: /matchups (kept for back-compat; nav label is now "Picks")
 * Query string ?tab=secondary deep-links to the secondary sub-tab.
 */
import { useEffect, useMemo, useState } from "react"
import { useSearchParams } from "react-router-dom"
import { ChevronDown } from "lucide-react"

import { MatchupExpandDetail } from "@/components/cockpit/matchup-expand-detail"
import {
  WorkspaceEmptyState,
  WorkspaceErrorState,
  WorkspaceLoadingState,
} from "@/components/monitoring/dashboard/workspace-grade-cells"
import { BarTrendChart } from "@/components/charts"
import { EdgeBadge, TierBadge } from "@/components/ui/edge-badge"
import { FilterBar } from "@/components/ui/filter-bar"
import { FilterSheet } from "@/components/ui/filter-sheet"
import { PickRow } from "@/components/ui/pick-row"
import { ProDataGrid } from "@/components/ui/pro-data-grid"
import {
  buildFailedCandidateColumns,
  buildMatchupKey,
  buildPicksPageMatchupColumns,
  buildSecondaryColumns,
} from "@/lib/cockpit-columns"
import {
  buildReplayGeneratedMatchups,
  buildReplayGeneratedSecondaryBets,
} from "@/lib/cockpit-picks"
import { formatNumber } from "@/lib/format"
import { EV_BADGE_TOOLTIP, MATCHUP_DETAIL_TOOLTIPS, MATCHUP_TABLE_TOOLTIPS } from "@/lib/metric-tooltips"
import { CollapsibleSection } from "@/components/ui/collapsible-section"
import { EmptyState } from "@/components/ui/empty-state"
import { ErrorState, LoadingState } from "@/components/ui/feedback-state"
import { TerminalPageHeader } from "@/components/ui/terminal-page-header"
import { PicksTableScroll } from "@/components/ui/picks-table-scroll"
import { cn } from "@/lib/utils"
import type {
  FailedMatchupCandidate,
  FlattenedSecondaryBet,
  LiveTournamentSnapshot,
  MatchupBet,
  PastMarketPredictionRow,
} from "@/lib/types"
import { secondaryBadgeLabel } from "@/pages/page-shared"

type MatchupDiagnostics = NonNullable<LiveTournamentSnapshot["diagnostics"]>

type PicksTab = "matchups" | "secondary"

type PicksPageProps = {
  // Matchup picks (already filtered by user's slider/book/search)
  matchups: MatchupBet[]
  matchupsEmptyMessage: string
  matchupDiagnostics?: MatchupDiagnostics
  minEdgePct: number
  // Secondary picks
  secondaryBets: FlattenedSecondaryBet[]
  // Player drilldown (kept for parity with cockpit; clicking a row could trigger this later)
  onPlayerSelect?: (playerKey: string) => void
  marketRows?: PastMarketPredictionRow[]
  marketRowsLoading?: boolean
  marketRowsError?: string
  /** When set to lab, shows research-lane chip in header. */
  lane?: "production" | "lab"
  /** Embedded in dashboard Full picks tab — hides page chrome. */
  embedded?: boolean
  embeddedLoading?: boolean
  embeddedLoadingMessage?: string
  embeddedErrorMessage?: string
  secondaryEmptyMessage?: string
}

type AvailabilityFilter = "all" | "available" | "unavailable"

type InventoryRow = {
  row: PastMarketPredictionRow
  availableNow: boolean
  firstSeenAt?: string | null
  lastSeenAt?: string | null
}

function marketRowKey(row: PastMarketPredictionRow): string {
  return [
    row.market_family ?? "",
    row.market_type ?? "",
    row.player_key ?? "",
    row.opponent_key ?? "",
    row.book ?? "",
    row.odds ?? "",
  ].join("|")
}

function tsToEpoch(value?: string | null): number {
  if (!value) return 0
  const parsed = Date.parse(value)
  return Number.isFinite(parsed) ? parsed : 0
}

function buildMarketInventory(rows: PastMarketPredictionRow[]): InventoryRow[] {
  if (!rows.length) return []

  const latestGeneratedAt = rows.reduce<string | null>((latest, row) => {
    const ts = row.generated_at ?? null
    if (!latest) return ts
    if (!ts) return latest
    return ts > latest ? ts : latest
  }, null)

  const availableKeys = new Set(
    rows
      .filter((row) => (row.generated_at ?? null) === latestGeneratedAt)
      .map((row) => marketRowKey(row)),
  )

  const grouped = new Map<string, InventoryRow>()
  for (const row of rows) {
    const key = marketRowKey(row)
    const existing = grouped.get(key)
    if (!existing) {
      grouped.set(key, {
        row,
        availableNow: availableKeys.has(key),
        firstSeenAt: row.generated_at ?? null,
        lastSeenAt: row.generated_at ?? null,
      })
      continue
    }
    const firstSeenAt =
      tsToEpoch(row.generated_at) < tsToEpoch(existing.firstSeenAt)
        ? row.generated_at ?? existing.firstSeenAt
        : existing.firstSeenAt
    const lastSeenAt =
      tsToEpoch(row.generated_at) > tsToEpoch(existing.lastSeenAt)
        ? row.generated_at ?? existing.lastSeenAt
        : existing.lastSeenAt
    const latestRow =
      tsToEpoch(row.generated_at) > tsToEpoch(existing.row.generated_at)
        ? row
        : existing.row
    grouped.set(key, {
      row: latestRow,
      availableNow: existing.availableNow || availableKeys.has(key),
      firstSeenAt,
      lastSeenAt,
    })
  }

  return Array.from(grouped.values()).sort((left, right) => {
    if (left.availableNow !== right.availableNow) {
      return left.availableNow ? -1 : 1
    }
    const edgeDelta =
      Number(right.row.ev ?? 0) - Number(left.row.ev ?? 0)
    if (edgeDelta !== 0) return edgeDelta
    return tsToEpoch(right.lastSeenAt) - tsToEpoch(left.lastSeenAt)
  })
}

/* ── Mini components ─────────────────────────────────────────────────── */

/* ── Sub-tab pill switcher ────────────────────────────────────────────── */

function PicksTabSwitcher({
  value,
  onChange,
  matchupCount,
  secondaryCount,
}: {
  value: PicksTab
  onChange: (next: PicksTab) => void
  matchupCount: number
  secondaryCount: number
}) {
  const tabs: Array<{ value: PicksTab; label: string; count: number }> = [
    { value: "matchups", label: "Matchups", count: matchupCount },
    { value: "secondary", label: "Secondary", count: secondaryCount },
  ]
  return (
    <div className="mode-switcher picks-mode-switcher" role="tablist" aria-label="Picks sub-tabs">
      {tabs.map((tab) => {
        const active = tab.value === value
        return (
          <button
            key={tab.value}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(tab.value)}
            className={cn("mode-tab", active && "active")}
            data-testid={`picks-tab-${tab.value}`}
          >
            {tab.label}
            <span className={cn("mode-tab-count", active && "mode-tab-count--active")}>{tab.count}</span>
          </button>
        )
      })}
    </div>
  )
}

function AvailabilityFilterBar({
  value,
  onChange,
  counts,
}: {
  value: AvailabilityFilter
  onChange: (next: AvailabilityFilter) => void
  counts: { all: number; available: number; unavailable: number }
}) {
  const options: Array<{ value: AvailabilityFilter; label: string; count: number }> = [
    { value: "all", label: "All tracked", count: counts.all },
    { value: "available", label: "Available", count: counts.available },
    { value: "unavailable", label: "No longer available", count: counts.unavailable },
  ]
  return (
    <div className="picks-availability-bar" aria-label="Availability filter">
      {options.map((option) => {
        const active = value === option.value
        return (
          <button
            key={option.value}
            type="button"
            onClick={() => onChange(option.value)}
            className={cn("mode-tab picks-availability-tab", active && "active")}
          >
            {option.label}
            <span className={cn("mode-tab-count", active && "mode-tab-count--active")}>{option.count}</span>
          </button>
        )
      })}
    </div>
  )
}

/* ── Diagnostics strip — shown above matchup table to make the algo transparent ── */

function MatchupDiagnosticsStrip({
  diagnostics,
  minEdgePct,
  visibleRowCount,
}: {
  diagnostics?: MatchupDiagnostics
  minEdgePct: number
  visibleRowCount: number
}) {
  if (!diagnostics) return null

  const inputRows = diagnostics.selection_counts?.input_rows ?? 0
  const qualifyingRows = diagnostics.selection_counts?.all_qualifying_rows ?? 0
  const selectedRows = diagnostics.selection_counts?.selected_rows ?? 0
  const booksSeen = diagnostics.books_seen?.length ?? 0
  const state = diagnostics.state ?? "unknown"
  const adaptation = diagnostics.adaptation_state ?? "normal"

  // Reason codes — only show non-zero
  const reasonEntries = Object.entries(diagnostics.reason_codes ?? {})
    .filter(([, count]) => Number(count) > 0)
    .sort((a, b) => Number(b[1]) - Number(a[1]))

  // Friendly state label
  const stateLabel: Record<string, string> = {
    edges_available: "Edges available",
    market_available_no_edges: "Markets posted, no edges cleared thresholds",
    no_market_posted_yet: "Markets not posted yet",
    pipeline_error: "Pipeline error",
    suppressed_by_adaptation: "Suppressed by adaptation guardrails",
  }

  // Friendly reason code labels
  const reasonLabel: Record<string, string> = {
    below_ev_threshold: "Below EV threshold",
    missing_player_name: "Missing player name",
    missing_composite_player: "Missing composite score",
    equal_composite_gap: "Equal composite gap",
    dg_model_disagreement: "DG / model disagreement",
    invalid_implied_prob: "Invalid implied prob",
    exposure_capped: "Per-player exposure capped",
  }

  return (
    <CollapsibleSection
      className="matchup-diagnostics-panel"
      title="Matchup pipeline"
      description={`${visibleRowCount} showing · min edge ${minEdgePct}%`}
      testId="matchup-diagnostics-strip"
    >
      <div className="matchup-diagnostics-stats">
        <DiagStat label="State" value={stateLabel[state] ?? state} />
        <DiagStat label="Candidates" value={inputRows.toString()} />
        <DiagStat label="Cleared algo" value={qualifyingRows.toString()} />
        <DiagStat label="Card-curated" value={selectedRows.toString()} />
        <DiagStat label="Showing" value={visibleRowCount.toString()} />
        <DiagStat label="Books" value={booksSeen.toString()} />
        <DiagStat label="Min edge" value={`${minEdgePct}%`} />
        {adaptation !== "normal" && <DiagStat label="Adaptation" value={adaptation} tone="warn" />}
      </div>

      {reasonEntries.length > 0 && (
        <div className="matchup-diagnostics-reasons">
          <span className="matchup-diagnostics-reasons-label">Filtered:</span>
          {reasonEntries.map(([code, count]) => (
            <span key={code}>
              <span className="text-muted-11">{reasonLabel[code] ?? code}</span>
              <span className="diag-stat-value" style={{ marginLeft: 4 }}>
                {count}
              </span>
            </span>
          ))}
        </div>
      )}

      {(diagnostics.errors?.length ?? 0) > 0 && (
        <div className="matchup-diagnostics-errors">
          {diagnostics.errors?.map((err, i) => (
            <div key={i}>⚠ {err}</div>
          ))}
        </div>
      )}
    </CollapsibleSection>
  )
}

function DiagStat({ label, value, tone }: { label: string; value: string; tone?: "warn" }) {
  return (
    <div className="diag-stat">
      <span className="diag-stat-label">{label}</span>
      <span className={tone === "warn" ? "diag-stat-value diag-stat-value--warn" : "diag-stat-value"}>
        {value}
      </span>
    </div>
  )
}

/* ── Failed candidates table — "show all candidates" view ───────────────── */

function FailedCandidatesTable({ candidates }: { candidates: FailedMatchupCandidate[] }) {
  const columns = useMemo(() => buildFailedCandidateColumns(), [])
  if (candidates.length === 0) return null
  return (
    <div className="card failed-candidates-card" data-testid="failed-candidates-table">
      <div className="card-header failed-candidates-header">
        <div className="card-title">All candidates considered</div>
        <div className="card-desc">{candidates.length} rows · ranked by EV (closest to clearing first)</div>
      </div>
      <div className="card-body failed-candidates-body">
        <ProDataGrid
          data={candidates}
          columns={columns}
          density="compact"
          getRowId={(row) => `${row.pick}-${row.opponent}-${row.book ?? "none"}`}
          testId="failed-candidates-grid"
        />
      </div>
    </div>
  )
}

/* ── Matchups sub-tab ─────────────────────────────────────────────────── */

function MatchupsBoard({
  matchups,
  emptyMessage,
  diagnostics,
  minEdgePct,
  embedded = false,
}: {
  matchups: MatchupBet[]
  emptyMessage: string
  diagnostics?: MatchupDiagnostics
  minEdgePct: number
  embedded?: boolean
}) {
  const [expandedKey, setExpandedKey] = useState<string | null>(null)
  const failedCandidates = (diagnostics?.failed_candidates ?? []) as FailedMatchupCandidate[]
  const [showAll, setShowAll] = useState<boolean>(matchups.length === 0)
  const matchupColumns = useMemo(() => buildPicksPageMatchupColumns(), [])

  const renderMatchupSubRow = (matchup: MatchupBet) => (
    <div className="matchup-detail-stack">
      <MatchupExpandDetail matchup={matchup} />
      <div className="matchup-detail-chart">
        <BarTrendChart
          labels={["Composite", "Form", "Course", "Momentum", "Conviction"]}
          values={[
            matchup.composite_gap,
            matchup.form_gap,
            matchup.course_fit_gap,
            Number(matchup.pick_momentum ?? 0) - Number(matchup.opp_momentum ?? 0),
            Number(matchup.conviction ?? 0),
          ]}
          color="#22C55E"
        />
      </div>
    </div>
  )

  return (
    <>
      <MatchupDiagnosticsStrip
        diagnostics={diagnostics}
        minEdgePct={minEdgePct}
        visibleRowCount={matchups.length}
      />
      {failedCandidates.length > 0 && (
        <div className="candidates-toggle-row">
          <label className="candidates-toggle-label" data-testid="show-all-candidates-toggle">
            <input
              type="checkbox"
              checked={showAll}
              onChange={(e) => setShowAll(e.target.checked)}
            />
            Show all candidates ({failedCandidates.length})
          </label>
        </div>
      )}
      <div className="card">
        {matchups.length > 0 ? (
          embedded ? (
            <div className="workspace-top-plays" data-testid="picks-embedded-matchups">
              {matchups.map((matchup) => {
                const key = buildMatchupKey(matchup)
                return (
                  <PickRow
                    key={key}
                    bet={matchup}
                    expanded={expandedKey === key}
                    onExpand={() => {
                      setExpandedKey((current) => (current === key ? null : key))
                    }}
                  />
                )
              })}
            </div>
          ) : (
            <ProDataGrid
              data={matchups}
              columns={matchupColumns}
              density="compact"
              virtualizeAfter={80}
              getRowId={(m) => buildMatchupKey(m)}
              getRowTestId={(m) => `matchup-row-${buildMatchupKey(m)}`}
              expandedRowId={expandedKey}
              onRowClick={(m) => {
                const key = buildMatchupKey(m)
                setExpandedKey(expandedKey === key ? null : key)
              }}
              renderSubRow={renderMatchupSubRow}
              testId="picks-matchups-grid"
            />
          )
        ) : (
          <div className="card-body">
            {embedded ? (
              <WorkspaceEmptyState message={emptyMessage} />
            ) : (
              <EmptyState
                message={emptyMessage}
                description="Try lowering the min edge threshold or selecting more books on the dashboard."
                className="empty-state--padded"
              />
            )}
          </div>
        )}
      </div>
      {showAll && failedCandidates.length > 0 ? (
        <FailedCandidatesTable candidates={failedCandidates} />
      ) : null}
    </>
  )
}

/* ── Secondary sub-tab ────────────────────────────────────────────────── */

function SecondaryBoard({
  bets,
  onPlayerSelect,
  isPast = false,
  embedded = false,
  emptyMessage = "No secondary-market edges available right now.",
}: {
  bets: FlattenedSecondaryBet[]
  onPlayerSelect?: (playerKey: string) => void
  isPast?: boolean
  embedded?: boolean
  emptyMessage?: string
}) {
  const grouped = useMemo(() => {
    const map = new Map<string, FlattenedSecondaryBet[]>()
    for (const bet of bets) {
      const list = map.get(bet.market) ?? []
      list.push(bet)
      map.set(bet.market, list)
    }
    for (const list of map.values()) {
      list.sort((a, b) => b.ev - a.ev)
    }
    return Array.from(map.entries())
  }, [bets])

  const secondaryColumns = useMemo(
    () =>
      buildSecondaryColumns({
        isPast,
        onPlayerSelect: (key) => onPlayerSelect?.(key),
      }),
    [isPast, onPlayerSelect],
  )

  if (bets.length === 0) {
    return (
      <div className="card">
        <div className="card-body">
          {embedded ? (
            <WorkspaceEmptyState message={emptyMessage} />
          ) : (
            <EmptyState
              message={emptyMessage}
              description="Top-finish, make-cut, and outright markets are scanned every refresh. Edges appear when book pricing diverges from the model."
              className="empty-state--padded"
            />
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="picks-secondary-stack">
      {grouped.map(([market, marketBets]) => (
        <div key={market} className="card secondary-grid-card">
          <div className="card-header">
            <div className="card-title">{secondaryBadgeLabel(market)}</div>
            <div className="card-desc">{marketBets.length} edges</div>
          </div>
          <ProDataGrid
            data={marketBets}
            columns={secondaryColumns}
            density="compact"
            getRowId={(row) => `${row.market}-${row.player}-${row.odds}`}
            getRowTestId={(row) => `secondary-row-${row.player}`}
            onRowClick={(row) => {
              if (row.player_key) onPlayerSelect?.(row.player_key)
            }}
            getRowClassName={(row) => (row.player_key ? "row-clickable" : undefined)}
            testId={`secondary-grid-${market}`}
          />
        </div>
      ))}
    </div>
  )
}

/* ── Page shell ───────────────────────────────────────────────────────── */

export function PicksPage({
  matchups,
  matchupsEmptyMessage,
  matchupDiagnostics,
  minEdgePct,
  secondaryBets,
  onPlayerSelect,
  marketRows = [],
  marketRowsLoading = false,
  marketRowsError,
  lane = "production",
  embedded = false,
  embeddedLoading = false,
  embeddedLoadingMessage = "Loading picks for this board…",
  embeddedErrorMessage,
  secondaryEmptyMessage,
}: PicksPageProps) {
  const [searchParams, setSearchParams] = useSearchParams()
  const initialTab: PicksTab = searchParams.get("tab") === "secondary" ? "secondary" : "matchups"
  const [tab, setTab] = useState<PicksTab>(initialTab)
  const [availabilityFilter, setAvailabilityFilter] = useState<AvailabilityFilter>("all")

  const marketInventory = useMemo(
    () => buildMarketInventory(marketRows),
    [marketRows],
  )
  const hasTrackedInventory = marketInventory.length > 0
  const filteredInventoryRows = useMemo(() => {
    if (!hasTrackedInventory) return []
    if (availabilityFilter === "all") return marketInventory
    const wantAvailable = availabilityFilter === "available"
    return marketInventory.filter((entry) => entry.availableNow === wantAvailable)
  }, [availabilityFilter, hasTrackedInventory, marketInventory])
  const replayRowsForFilter = useMemo(
    () => filteredInventoryRows.map((entry) => entry.row),
    [filteredInventoryRows],
  )

  const matchupSource = hasTrackedInventory
    ? buildReplayGeneratedMatchups(
        replayRowsForFilter.filter((row) => row.market_family === "matchup"),
      )
    : matchups
  const secondarySource = hasTrackedInventory
    ? buildReplayGeneratedSecondaryBets(
        replayRowsForFilter.filter((row) => row.market_family !== "matchup"),
      )
    : secondaryBets
  const availabilityCounts = useMemo(() => {
    if (!hasTrackedInventory) {
      return {
        all: matchups.length + secondaryBets.length,
        available: matchups.length + secondaryBets.length,
        unavailable: 0,
      }
    }
    const available = marketInventory.filter((entry) => entry.availableNow).length
    const unavailable = marketInventory.length - available
    return {
      all: marketInventory.length,
      available,
      unavailable,
    }
  }, [hasTrackedInventory, marketInventory, matchups.length, secondaryBets.length])

  // Keep ?tab= param in sync so refresh / deep-links work
  useEffect(() => {
    const current = searchParams.get("tab")
    if (tab === "secondary" && current !== "secondary") {
      const next = new URLSearchParams(searchParams)
      next.set("tab", "secondary")
      setSearchParams(next, { replace: true })
    } else if (tab === "matchups" && current === "secondary") {
      const next = new URLSearchParams(searchParams)
      next.delete("tab")
      setSearchParams(next, { replace: true })
    }
  }, [searchParams, setSearchParams, tab])

  const description =
    tab === "matchups"
      ? `${matchupSource.length} tracked matchup lines · click any row to expand`
      : `${secondarySource.length} tracked secondary lines across top-finish, make-cut & outright markets`

  const stateLoading = embeddedLoading || marketRowsLoading
  const stateErrorMessage = embeddedErrorMessage ?? (marketRowsError ? `Inventory history unavailable: ${marketRowsError}` : null)

  return (
    <div className={embedded ? "picks-page-embed" : "page-shell picks-page-shell"}>
      {!embedded ? (
        <TerminalPageHeader
          eyebrow={lane === "lab" ? "Lab lane" : "Matchups workspace"}
          title="Picks"
          description={description}
          action={lane === "lab" ? <span className="lane-chip">Lab lane</span> : undefined}
          kpis={
            <div className="terminal-kpi-strip">
              <span className="terminal-kpi">
                <span className="terminal-kpi-label">Matchups</span>
                <span className="terminal-kpi-value">{matchupSource.length}</span>
              </span>
              <span className="terminal-kpi">
                <span className="terminal-kpi-label">Secondary</span>
                <span className="terminal-kpi-value">{secondarySource.length}</span>
              </span>
              <span className="terminal-kpi">
                <span className="terminal-kpi-label">Min edge</span>
                <span className="terminal-kpi-value">{minEdgePct}%</span>
              </span>
            </div>
          }
        />
      ) : null}

      <div className={embedded ? "picks-page-filters-sticky picks-page-filters-sticky--embed" : "picks-page-filters-sticky"}>
      <PicksTabSwitcher
        value={tab}
        onChange={setTab}
        matchupCount={matchupSource.length}
        secondaryCount={secondarySource.length}
      />
      <FilterSheet title="Picks filters" description="Availability for tracked lines">
        <AvailabilityFilterBar
          value={availabilityFilter}
          onChange={setAvailabilityFilter}
          counts={availabilityCounts}
        />
      </FilterSheet>
      </div>
      {stateLoading ? (
        embedded ? (
          <WorkspaceLoadingState message={embeddedLoadingMessage} />
        ) : (
          <LoadingState message="Syncing tracked pick inventory…" />
        )
      ) : null}
      {stateErrorMessage ? (
        embedded ? (
          <WorkspaceErrorState message={stateErrorMessage} />
        ) : (
          <ErrorState message={stateErrorMessage} />
        )
      ) : null}

      {tab === "matchups" ? (
        <MatchupsBoard
          matchups={matchupSource}
          emptyMessage={matchupsEmptyMessage}
          diagnostics={matchupDiagnostics}
          minEdgePct={minEdgePct}
          embedded={embedded}
        />
      ) : (
        <SecondaryBoard
          bets={secondarySource}
          onPlayerSelect={onPlayerSelect}
          embedded={embedded}
          emptyMessage={secondaryEmptyMessage}
        />
      )}
    </div>
  )
}
