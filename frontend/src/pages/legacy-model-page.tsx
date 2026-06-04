import type { ColumnDef } from "@tanstack/react-table"
import { useMemo } from "react"
import { Link } from "react-router-dom"

import { ProDataGrid } from "@/components/ui/pro-data-grid"
import { TerminalPageHeader } from "@/components/ui/terminal-page-header"
import type { LiveRefreshSnapshot } from "@/lib/types"

type LegacyRanking = {
  player_key?: string
  player: string
  rank: number
  composite: number
  course_fit: number
  form: number
  momentum: number
}

type LegacyMatchup = {
  pick_key: string
  opponent_key: string
  pick: string
  opponent: string
  book?: string | null
  odds: number | string
  ev_pct?: string | null
  tier?: string | null
}

function buildLegacyRankingColumns(): ColumnDef<LegacyRanking, unknown>[] {
  return [
    { id: "rank", accessorKey: "rank", header: "Rank", meta: { label: "Rank", mono: true } },
    { id: "player", accessorKey: "player", header: "Player", meta: { label: "Player", sticky: true } },
    {
      id: "composite",
      accessorKey: "composite",
      header: "Composite",
      meta: { label: "Composite", align: "right", mono: true },
      cell: ({ getValue }) => <span className="num metric">{(getValue() as number).toFixed(1)}</span>,
    },
    {
      id: "course",
      accessorKey: "course_fit",
      header: "Course",
      meta: { label: "Course", align: "right", mono: true },
      cell: ({ getValue }) => <span className="num metric">{(getValue() as number).toFixed(1)}</span>,
    },
    {
      id: "form",
      accessorKey: "form",
      header: "Form",
      meta: { label: "Form", align: "right", mono: true },
      cell: ({ getValue }) => <span className="num metric">{(getValue() as number).toFixed(1)}</span>,
    },
    {
      id: "momentum",
      accessorKey: "momentum",
      header: "Momentum",
      meta: { label: "Momentum", align: "right", mono: true },
      cell: ({ getValue }) => <span className="num metric">{(getValue() as number).toFixed(1)}</span>,
    },
  ]
}

function buildLegacyMatchupColumns(): ColumnDef<LegacyMatchup, unknown>[] {
  return [
    { id: "pick", accessorKey: "pick", header: "Pick", meta: { label: "Pick", sticky: true } },
    { id: "opponent", accessorKey: "opponent", header: "Opponent", meta: { label: "Opponent" } },
    {
      id: "book",
      accessorKey: "book",
      header: "Book",
      meta: { label: "Book" },
      cell: ({ getValue }) => <span>{(getValue() as string | null) ?? "—"}</span>,
    },
    {
      id: "odds",
      accessorKey: "odds",
      header: "Odds",
      meta: { label: "Odds", align: "right", mono: true },
      cell: ({ getValue }) => <span className="num metric">{String(getValue() ?? "—")}</span>,
    },
    {
      id: "edge",
      accessorKey: "ev_pct",
      header: "Edge",
      meta: { label: "Edge", align: "right", mono: true },
      cell: ({ getValue }) => <span className="num metric">{(getValue() as string | null) ?? "—"}</span>,
    },
    {
      id: "tier",
      accessorKey: "tier",
      header: "Tier",
      meta: { label: "Tier" },
      cell: ({ getValue }) => <span>{(getValue() as string | null) ?? "—"}</span>,
    },
  ]
}

export function LegacyModelPage({ liveSnapshot }: { liveSnapshot: LiveRefreshSnapshot | null }) {
  const legacy = liveSnapshot?.legacy_tournament
  const rankings = (legacy?.rankings ?? []).slice(0, 25) as LegacyRanking[]
  const matchupBets = (legacy?.matchup_bets_all_books ?? legacy?.matchup_bets ?? []).slice(
    0,
    25,
  ) as LegacyMatchup[]
  const diagnosticsErrors = legacy?.diagnostics?.errors ?? []

  const rankingColumns = useMemo(() => buildLegacyRankingColumns(), [])
  const matchupColumns = useMemo(() => buildLegacyMatchupColumns(), [])

  return (
    <div className="research-page">
      <TerminalPageHeader
        eyebrow="Research"
        title="Legacy model (baseline)"
        description="Read-only fallback lane for last month's baseline model."
        action={
          <Link to="/" className="btn btn-ghost btn-sm">
            Back to cockpit
          </Link>
        }
      />

      <div className="card research-card">
        <div className="card-body research-card-body">
          {!legacy ? (
            <div className="term-notice">
              Legacy baseline snapshot is not available yet. Refresh the live snapshot and try again.
            </div>
          ) : (
            <>
              <div className="term-notice">
                Event: {legacy.event_name ?? "Unknown"} · Variant: {legacy.model_variant ?? "baseline"} ·
                Source: {legacy.generated_from ?? "legacy_baseline_model"}
              </div>
              {diagnosticsErrors.length > 0 ? (
                <div className="term-notice" role="alert">
                  {diagnosticsErrors.join(" ")}
                </div>
              ) : null}

              <section className="research-section">
                <h2 className="research-section-heading">Top legacy rankings</h2>
                {rankings.length === 0 ? (
                  <div className="empty-state">
                    <div className="empty-state-title">No baseline rankings in this snapshot.</div>
                  </div>
                ) : (
                  <ProDataGrid
                    data={rankings}
                    columns={rankingColumns}
                    density="compact"
                    getRowId={(row) => `${row.player_key ?? row.player}-${row.rank}`}
                    testId="legacy-rankings-grid"
                  />
                )}
              </section>

              <section className="research-section">
                <h2 className="research-section-heading">Legacy matchup edges</h2>
                {matchupBets.length === 0 ? (
                  <div className="empty-state">
                    <div className="empty-state-title">No baseline matchup edges in this snapshot.</div>
                  </div>
                ) : (
                  <ProDataGrid
                    data={matchupBets}
                    columns={matchupColumns}
                    density="compact"
                    getRowId={(row) => `${row.pick_key}-${row.opponent_key}-${row.book}-${row.odds}`}
                    testId="legacy-matchups-grid"
                  />
                )}
              </section>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
