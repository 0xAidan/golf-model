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

import { BarTrendChart } from "@/components/charts"
import {
  buildReplayGeneratedMatchups,
  buildReplayGeneratedSecondaryBets,
} from "@/lib/cockpit-picks"
import { formatNumber } from "@/lib/format"
import {
  EV_BADGE_TOOLTIP,
  MATCHUP_DETAIL_TOOLTIPS,
  MATCHUP_TABLE_TOOLTIPS,
  TIER_BADGE_TOOLTIP,
} from "@/lib/metric-tooltips"
import { cn } from "@/lib/utils"
import type {
  FailedMatchupCandidate,
  FlattenedSecondaryBet,
  LiveTournamentSnapshot,
  MatchupBet,
  PastMarketPredictionRow,
} from "@/lib/types"
import { buildMatchupKey, secondaryBadgeLabel } from "@/pages/page-shared"

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

function EmptyState({ message, children }: { message: string; children?: React.ReactNode }) {
  return (
    <div className="empty-state" style={{ padding: "32px 16px" }}>
      <div className="empty-state-title">{message}</div>
      {children}
    </div>
  )
}

function EV({ ev, evPct }: { ev: number; evPct?: string }) {
  const cls = ev >= 0.08 ? "high" : ev >= 0.04 ? "medium" : "low"
  return (
    <span className={`ev-badge ${cls}`} title={EV_BADGE_TOOLTIP} style={{ cursor: "help" }}>
      {evPct ?? `${(ev * 100).toFixed(1)}%`}
    </span>
  )
}

function TierBadge({ tier }: { tier?: string }) {
  const t = (tier ?? "LEAN").toUpperCase()
  return (
    <span className={`tier-badge ${t}`} title={TIER_BADGE_TOOLTIP} style={{ cursor: "help" }}>
      {t}
    </span>
  )
}

function PageHeader({ title, description }: { title: string; description?: string }) {
  return (
    <div style={{ marginBottom: 10, display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
      <div
        style={{
          fontFamily: "var(--font-mono)",
          fontSize: 10,
          fontWeight: 700,
          letterSpacing: "0.14em",
          textTransform: "uppercase",
          color: "var(--text-muted)",
        }}
      >
        {title}
      </div>
      {description && (
        <div style={{ fontSize: 11, color: "var(--text-faint)", fontFamily: "var(--font-mono)" }}>
          {description}
        </div>
      )}
    </div>
  )
}

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
    <div className="mode-switcher" role="tablist" aria-label="Picks sub-tabs" style={{ marginBottom: 12 }}>
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
            <span
              style={{
                marginLeft: 6,
                padding: "1px 6px",
                borderRadius: 8,
                fontSize: 9,
                fontWeight: 700,
                background: active ? "rgba(34,197,94,0.15)" : "var(--surface-2)",
                color: active ? "var(--green)" : "var(--text-muted)",
                fontVariantNumeric: "tabular-nums",
              }}
            >
              {tab.count}
            </span>
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
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        gap: 8,
        marginBottom: 10,
      }}
      aria-label="Availability filter"
    >
      {options.map((option) => {
        const active = value === option.value
        return (
          <button
            key={option.value}
            type="button"
            onClick={() => onChange(option.value)}
            className={cn("mode-tab", active && "active")}
            style={{ minHeight: 30 }}
          >
            {option.label}
            <span
              style={{
                marginLeft: 6,
                padding: "1px 6px",
                borderRadius: 8,
                fontSize: 9,
                fontWeight: 700,
                background: active ? "rgba(34,197,94,0.15)" : "var(--surface-2)",
                color: active ? "var(--green)" : "var(--text-muted)",
                fontVariantNumeric: "tabular-nums",
              }}
            >
              {option.count}
            </span>
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
    <div
      className="card"
      style={{
        padding: "10px 12px",
        marginBottom: 8,
        background: "var(--surface)",
        border: "1px solid var(--border)",
      }}
      data-testid="matchup-diagnostics-strip"
    >
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: 16,
          fontSize: 11,
          fontFamily: "var(--font-mono)",
          color: "var(--text-muted)",
        }}
      >
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
        <div
          style={{
            marginTop: 8,
            paddingTop: 8,
            borderTop: "1px solid var(--divider)",
            display: "flex",
            flexWrap: "wrap",
            gap: 12,
            fontSize: 10,
            fontFamily: "var(--font-mono)",
            color: "var(--text-faint)",
          }}
        >
          <span style={{ textTransform: "uppercase", letterSpacing: "0.1em", fontWeight: 700 }}>Filtered:</span>
          {reasonEntries.map(([code, count]) => (
            <span key={code}>
              <span style={{ color: "var(--text-muted)" }}>{reasonLabel[code] ?? code}</span>
              <span style={{ marginLeft: 4, color: "var(--text)" }}>{count}</span>
            </span>
          ))}
        </div>
      )}

      {(diagnostics.errors?.length ?? 0) > 0 && (
        <div
          style={{
            marginTop: 8,
            paddingTop: 8,
            borderTop: "1px solid var(--divider)",
            fontSize: 11,
            color: "var(--red)",
          }}
        >
          {diagnostics.errors?.map((err, i) => (
            <div key={i}>⚠ {err}</div>
          ))}
        </div>
      )}
    </div>
  )
}

function DiagStat({ label, value, tone }: { label: string; value: string; tone?: "warn" }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <span style={{ fontSize: 9, textTransform: "uppercase", letterSpacing: "0.1em", color: "var(--text-faint)" }}>
        {label}
      </span>
      <span
        style={{
          fontSize: 12,
          fontWeight: 600,
          color: tone === "warn" ? "var(--gold)" : "var(--text)",
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {value}
      </span>
    </div>
  )
}

/* ── Failed candidates table — "show all candidates" view ───────────────── */

function reasonBadge(reasonCode: string) {
  const map: Record<string, { label: string; color: string }> = {
    below_ev_threshold: { label: "Below EV", color: "var(--text-muted)" },
    dg_model_disagreement: { label: "DG disagree", color: "var(--gold)" },
  }
  const entry = map[reasonCode] ?? { label: reasonCode, color: "var(--text-muted)" }
  return (
    <span
      style={{
        fontSize: 9,
        fontFamily: "var(--font-mono)",
        textTransform: "uppercase",
        letterSpacing: "0.08em",
        padding: "2px 6px",
        borderRadius: 4,
        border: "1px solid var(--border)",
        color: entry.color,
        background: "var(--surface-2)",
        whiteSpace: "nowrap",
      }}
    >
      {entry.label}
    </span>
  )
}

function FailedCandidatesTable({ candidates }: { candidates: FailedMatchupCandidate[] }) {
  if (candidates.length === 0) return null
  return (
    <div className="card" style={{ marginTop: 8 }} data-testid="failed-candidates-table">
      <div
        className="card-header"
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 8,
        }}
      >
        <div className="card-title">All candidates considered</div>
        <div className="card-desc">{candidates.length} rows · ranked by EV (closest to clearing first)</div>
      </div>
      <div style={{ overflow: "auto" }}>
        <table className="data-table">
          <thead>
            <tr>
              <th title={MATCHUP_TABLE_TOOLTIPS.pickVsOpp}>Pick vs Opponent</th>
              <th title={MATCHUP_TABLE_TOOLTIPS.book}>Book</th>
              <th title={MATCHUP_TABLE_TOOLTIPS.odds}>Odds</th>
              <th className="center" title={MATCHUP_TABLE_TOOLTIPS.reason}>
                Reason
              </th>
              <th className="right" title={MATCHUP_TABLE_TOOLTIPS.ev}>
                EV
              </th>
              <th className="right" title={MATCHUP_TABLE_TOOLTIPS.winPct}>
                Win%
              </th>
            </tr>
          </thead>
          <tbody>
            {candidates.map((cand, idx) => {
              const winPct =
                cand.model_win_prob !== undefined && cand.model_win_prob !== null
                  ? `${(cand.model_win_prob * 100).toFixed(1)}%`
                  : "—"
              const evDisplay =
                cand.ev_pct ??
                (cand.ev !== null && cand.ev !== undefined ? `${(cand.ev * 100).toFixed(1)}%` : "—")
              return (
                <tr key={`${cand.pick}-${cand.opponent}-${cand.book ?? "none"}-${idx}`}>
                  <td>
                    <div style={{ fontWeight: 600, color: "var(--text)" }}>{cand.pick}</div>
                    <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 1 }}>
                      vs {cand.opponent}
                    </div>
                  </td>
                  <td style={{ color: "var(--text-muted)", fontSize: 12 }}>{cand.book ?? "—"}</td>
                  <td
                    style={{
                      fontWeight: 600,
                      color: "var(--text)",
                      fontVariantNumeric: "tabular-nums",
                    }}
                  >
                    {cand.odds ?? "—"}
                  </td>
                  <td className="center">{reasonBadge(cand.reason_code)}</td>
                  <td
                    className="right num"
                    title={EV_BADGE_TOOLTIP}
                    style={{
                      color:
                        cand.ev !== null && cand.ev !== undefined && cand.ev >= 0
                          ? "var(--text)"
                          : "var(--text-muted)",
                      cursor: "help",
                    }}
                  >
                    {evDisplay}
                  </td>
                  <td className="right num" title={MATCHUP_TABLE_TOOLTIPS.winPct} style={{ color: "var(--text-muted)", fontSize: 12, cursor: "help" }}>
                    {winPct}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
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
}: {
  matchups: MatchupBet[]
  emptyMessage: string
  diagnostics?: MatchupDiagnostics
  minEdgePct: number
}) {
  const [expandedKey, setExpandedKey] = useState<string | null>(null)
  const failedCandidates = (diagnostics?.failed_candidates ?? []) as FailedMatchupCandidate[]
  // Default ON when there are zero qualifying rows so the user immediately sees what was considered.
  const [showAll, setShowAll] = useState<boolean>(matchups.length === 0)

  return (
    <>
      <MatchupDiagnosticsStrip
        diagnostics={diagnostics}
        minEdgePct={minEdgePct}
        visibleRowCount={matchups.length}
      />
      {failedCandidates.length > 0 && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "flex-end",
            gap: 8,
            marginBottom: 8,
            fontSize: 11,
            fontFamily: "var(--font-mono)",
            color: "var(--text-muted)",
          }}
        >
          <label
            style={{ display: "inline-flex", alignItems: "center", gap: 6, cursor: "pointer" }}
            data-testid="show-all-candidates-toggle"
          >
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
          <div style={{ overflow: "auto" }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th title={MATCHUP_TABLE_TOOLTIPS.pickVsOpp}>Pick vs Opponent</th>
                  <th title={MATCHUP_TABLE_TOOLTIPS.book}>Book</th>
                  <th title={MATCHUP_TABLE_TOOLTIPS.odds}>Odds</th>
                  <th className="center" title={MATCHUP_TABLE_TOOLTIPS.tier}>
                    Tier
                  </th>
                  <th className="right" title={MATCHUP_TABLE_TOOLTIPS.ev}>
                    EV
                  </th>
                  <th className="right" title={MATCHUP_TABLE_TOOLTIPS.winPct}>
                    Win%
                  </th>
                  <th style={{ width: 32 }} />
                </tr>
              </thead>
              <tbody>
                {matchups.map((matchup) => {
                  const key = buildMatchupKey(matchup)
                  const isExpanded = expandedKey === key
                  return (
                    <>
                      <tr
                        key={key}
                        onClick={() => setExpandedKey(isExpanded ? null : key)}
                        style={{ cursor: "pointer" }}
                        data-testid={`matchup-row-${key}`}
                      >
                        <td>
                          <div style={{ fontWeight: 600, color: "var(--text)" }}>{matchup.pick}</div>
                          <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 1 }}>
                            vs {matchup.opponent}
                          </div>
                        </td>
                        <td style={{ color: "var(--text-muted)", fontSize: 12 }}>{matchup.book ?? "—"}</td>
                        <td
                          style={{
                            fontWeight: 600,
                            color: "var(--text)",
                            fontVariantNumeric: "tabular-nums",
                          }}
                        >
                          {matchup.odds}
                        </td>
                        <td className="center">
                          <TierBadge tier={matchup.tier} />
                        </td>
                        <td className="right">
                          <EV ev={matchup.ev} evPct={matchup.ev_pct} />
                        </td>
                        <td className="right num" title={MATCHUP_TABLE_TOOLTIPS.winPct} style={{ color: "var(--text-muted)", fontSize: 12, cursor: "help" }}>
                          {(matchup.model_win_prob * 100).toFixed(1)}%
                        </td>
                        <td style={{ textAlign: "center" }}>
                          <ChevronDown
                            size={14}
                            style={{
                              color: "var(--text-faint)",
                              transform: isExpanded ? "rotate(180deg)" : "none",
                              transition: "transform 180ms ease",
                            }}
                          />
                        </td>
                      </tr>
                      {isExpanded && (
                        <tr key={`${key}-detail`}>
                          <td colSpan={7} style={{ padding: 0 }}>
                            <div className="matchup-detail">
                              <div className="matchup-detail-grid">
                                <div>
                                  <div className="detail-item-label" title={MATCHUP_DETAIL_TOOLTIPS.compositeGap}>
                                    Composite gap
                                  </div>
                                  <div className="detail-item-value num">
                                    {formatNumber(matchup.composite_gap, 2)}
                                  </div>
                                </div>
                                <div>
                                  <div className="detail-item-label" title={MATCHUP_DETAIL_TOOLTIPS.formGap}>
                                    Form gap
                                  </div>
                                  <div className="detail-item-value num">
                                    {formatNumber(matchup.form_gap, 2)}
                                  </div>
                                </div>
                                <div>
                                  <div className="detail-item-label" title={MATCHUP_DETAIL_TOOLTIPS.courseGap}>
                                    Course gap
                                  </div>
                                  <div className="detail-item-value num">
                                    {formatNumber(matchup.course_fit_gap, 2)}
                                  </div>
                                </div>
                                <div>
                                  <div className="detail-item-label" title={MATCHUP_DETAIL_TOOLTIPS.impliedProb}>
                                    Implied prob
                                  </div>
                                  <div className="detail-item-value num">
                                    {(matchup.implied_prob * 100).toFixed(1)}%
                                  </div>
                                </div>
                                <div>
                                  <div className="detail-item-label" title={MATCHUP_DETAIL_TOOLTIPS.conviction}>
                                    Conviction
                                  </div>
                                  <div className="detail-item-value num">
                                    {formatNumber(matchup.conviction, 0)}
                                  </div>
                                </div>
                                <div>
                                  <div className="detail-item-label" title={MATCHUP_DETAIL_TOOLTIPS.momentum}>
                                    Momentum
                                  </div>
                                  <div
                                    className="detail-item-value"
                                    style={{
                                      color: matchup.momentum_aligned
                                        ? "var(--positive)"
                                        : "var(--text-muted)",
                                    }}
                                  >
                                    {matchup.momentum_aligned ? "Aligned ↑" : "Mixed"}
                                  </div>
                                </div>
                              </div>
                              {matchup.reason && (
                                <div
                                  style={{
                                    marginTop: 10,
                                    fontSize: 12,
                                    color: "var(--text-muted)",
                                    lineHeight: 1.6,
                                  }}
                                >
                                  {matchup.reason}
                                </div>
                              )}
                              <div style={{ marginTop: 12 }}>
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
                          </td>
                        </tr>
                      )}
                    </>
                  )
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="card-body">
            <EmptyState message={emptyMessage}>
              <div
                style={{
                  marginTop: 8,
                  fontSize: 11,
                  color: "var(--text-faint)",
                  fontFamily: "var(--font-mono)",
                  maxWidth: 480,
                  margin: "8px auto 0",
                  lineHeight: 1.6,
                }}
              >
                The model ran successfully — see the diagnostic strip above for the full breakdown of
                candidates examined, books polled, and the reason codes that filtered each row.
                {failedCandidates.length > 0 && " Toggle 'Show all candidates' above to see the gated rows."}
              </div>
            </EmptyState>
          </div>
        )}
      </div>
      {showAll && <FailedCandidatesTable candidates={failedCandidates} />}
    </>
  )
}

/* ── Secondary sub-tab ────────────────────────────────────────────────── */

function SecondaryBoard({
  bets,
  onPlayerSelect,
}: {
  bets: FlattenedSecondaryBet[]
  onPlayerSelect?: (playerKey: string) => void
}) {
  // Group by market for clarity
  const grouped = useMemo(() => {
    const map = new Map<string, FlattenedSecondaryBet[]>()
    for (const bet of bets) {
      const list = map.get(bet.market) ?? []
      list.push(bet)
      map.set(bet.market, list)
    }
    // Sort each group by EV desc; preserve input market order
    for (const list of map.values()) {
      list.sort((a, b) => b.ev - a.ev)
    }
    return Array.from(map.entries())
  }, [bets])

  if (bets.length === 0) {
    return (
      <div className="card">
        <div className="card-body">
          <EmptyState message="No secondary-market edges available right now.">
            <div
              style={{
                marginTop: 8,
                fontSize: 11,
                color: "var(--text-faint)",
                fontFamily: "var(--font-mono)",
                maxWidth: 480,
                margin: "8px auto 0",
                lineHeight: 1.6,
              }}
            >
              Top-finish, make-cut, and outright markets are scanned every refresh. Edges appear here
              when book pricing diverges from the model by enough to clear EV thresholds.
            </div>
          </EmptyState>
        </div>
      </div>
    )
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {grouped.map(([market, marketBets]) => (
        <div key={market} className="card">
          <div className="card-header">
            <div className="card-title">{secondaryBadgeLabel(market)}</div>
            <div className="card-desc">{marketBets.length} edges</div>
          </div>
          <div style={{ overflow: "auto" }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th title={MATCHUP_TABLE_TOOLTIPS.player}>Player</th>
                  <th className="center" title={MATCHUP_TABLE_TOOLTIPS.tier}>
                    Tier
                  </th>
                  <th title={MATCHUP_TABLE_TOOLTIPS.bookOdds}>Book · Odds</th>
                  <th className="right" title={MATCHUP_TABLE_TOOLTIPS.ev}>
                    EV
                  </th>
                </tr>
              </thead>
              <tbody>
                {marketBets.map((bet) => {
                  const tier = (bet.confidence ?? "LEAN").toUpperCase()
                  return (
                    <tr
                      key={`${bet.market}-${bet.player}-${bet.odds}`}
                      onClick={() => bet.player_key && onPlayerSelect?.(bet.player_key)}
                      style={{ cursor: bet.player_key ? "pointer" : "default" }}
                      data-testid={`secondary-row-${bet.player}`}
                    >
                      <td className="player-name">
                        <div style={{ fontWeight: 600, color: "var(--text)" }}>{bet.player}</div>
                      </td>
                      <td className="center">
                        <TierBadge tier={tier} />
                      </td>
                      <td style={{ fontSize: 12, color: "var(--text-muted)" }}>
                        {bet.book ? `${bet.book} · ${bet.odds}` : bet.odds}
                      </td>
                      <td className="right">
                        <EV ev={bet.ev} />
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
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

  return (
    <div
      style={{
        flex: 1,
        overflowY: "auto",
        padding: "10px 12px",
        display: "flex",
        flexDirection: "column",
        gap: 4,
      }}
    >
      <PageHeader title="Picks" description={description} />

      <PicksTabSwitcher
        value={tab}
        onChange={setTab}
        matchupCount={matchupSource.length}
        secondaryCount={secondarySource.length}
      />
      <AvailabilityFilterBar
        value={availabilityFilter}
        onChange={setAvailabilityFilter}
        counts={availabilityCounts}
      />
      {marketRowsLoading && (
        <div style={{ marginBottom: 8, fontSize: 11, color: "var(--text-faint)", fontFamily: "var(--font-mono)" }}>
          Syncing tracked pick inventory…
        </div>
      )}
      {marketRowsError && (
        <div style={{ marginBottom: 8, fontSize: 11, color: "var(--gold)", fontFamily: "var(--font-mono)" }}>
          Inventory history unavailable: {marketRowsError}
        </div>
      )}

      {tab === "matchups" ? (
        <MatchupsBoard
          matchups={matchupSource}
          emptyMessage={matchupsEmptyMessage}
          diagnostics={matchupDiagnostics}
          minEdgePct={minEdgePct}
        />
      ) : (
        <SecondaryBoard bets={secondarySource} onPlayerSelect={onPlayerSelect} />
      )}
    </div>
  )
}
