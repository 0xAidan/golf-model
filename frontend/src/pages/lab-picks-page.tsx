/**
 * Lab sandbox picks — same tables as /matchups but fed from ``lab_*`` snapshot sections
 * and logs to ``picks`` with ``source=lab_sandbox`` via POST /api/lab/log-displayed-picks.
 */
import { useMutation } from "@tanstack/react-query"
import { useMemo, useState } from "react"

import { api } from "@/lib/api"
import type {
  FlattenedSecondaryBet,
  LiveTournamentSnapshot,
  MatchupBet,
  PastMarketPredictionRow,
  PredictionRunResponse,
} from "@/lib/types"
import { PicksPage } from "@/pages/picks-page"

type MatchupDiagnostics = NonNullable<LiveTournamentSnapshot["diagnostics"]>

export type LabPicksPageProps = {
  matchups: MatchupBet[]
  matchupsEmptyMessage: string
  matchupDiagnostics?: MatchupDiagnostics
  minEdgePct: number
  secondaryBets: FlattenedSecondaryBet[]
  onPlayerSelect?: (playerKey: string) => void
  marketRows?: PastMarketPredictionRow[]
  marketRowsLoading?: boolean
  marketRowsError?: string
  tournamentId: number | null | undefined
  profileName?: string
  predictionRun: PredictionRunResponse | null
}

export const LabPicksPage = ({
  matchups,
  matchupsEmptyMessage,
  matchupDiagnostics,
  minEdgePct,
  secondaryBets,
  onPlayerSelect,
  marketRows,
  marketRowsLoading,
  marketRowsError,
  tournamentId,
  profileName = "lab_sandbox",
  predictionRun,
}: LabPicksPageProps) => {
  const [logMessage, setLogMessage] = useState<string | null>(null)
  const logMutation = useMutation({
    mutationFn: () => {
      if (tournamentId === null || tournamentId === undefined) {
        throw new Error("Missing tournament_id for lab picks logging.")
      }
      const matchupsPayload = matchups.map((m) => ({
        pick_key: m.pick_key,
        opponent_key: m.opponent_key,
        pick: m.pick,
        opponent: m.opponent,
        odds: m.odds,
        book: m.book,
        ev: m.ev,
        model_win_prob: m.model_win_prob,
        implied_prob: m.implied_prob,
        tier: m.tier,
        why: m.reason,
      }))
      return api.postLabLogDisplayedPicks({
        tournament_id: tournamentId,
        profile_name: profileName,
        composite_results: predictionRun?.composite_results ?? [],
        matchups: matchupsPayload,
      })
    },
    onSuccess: (res) => {
      if (res.ok) {
        setLogMessage(`Logged ${res.rows_written ?? 0} pick row(s) for lab grading.`)
      } else {
        setLogMessage(res.error ?? "Log request failed.")
      }
    },
    onError: (err: Error) => {
      setLogMessage(err.message ?? "Log failed.")
    },
  })

  const logDisabled = useMemo(() => {
    if (tournamentId === null || tournamentId === undefined) return true
    if (!matchups.length) return true
    return false
  }, [tournamentId, matchups.length])

  return (
    <div style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}>
      <div
        className="term-notice"
        style={{ margin: "8px 12px 0", fontSize: 12, lineHeight: 1.45 }}
        data-testid="lab-picks-banner"
      >
        <strong>Lab picks</strong> — uses the parallel lab snapshot lane only. Logging writes{" "}
        <code style={{ fontSize: 11 }}>source=lab_sandbox</code> rows; production <strong>/matchups</strong> is
        unchanged.
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 12px", flexShrink: 0 }}>
        <button
          type="button"
          className="btn btn-primary"
          disabled={logDisabled || logMutation.isPending}
          onClick={() => {
            setLogMessage(null)
            logMutation.mutate()
          }}
          data-testid="lab-picks-log-btn"
        >
          {logMutation.isPending ? "Logging…" : "Log displayed lab picks for grading"}
        </button>
        {logMessage && (
          <span style={{ fontSize: 11, color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>{logMessage}</span>
        )}
      </div>
      <div style={{ flex: 1, minHeight: 0, overflow: "hidden", display: "flex", flexDirection: "column" }}>
        <PicksPage
          matchups={matchups}
          matchupsEmptyMessage={matchupsEmptyMessage}
          matchupDiagnostics={matchupDiagnostics}
          minEdgePct={minEdgePct}
          secondaryBets={secondaryBets}
          onPlayerSelect={onPlayerSelect}
          marketRows={marketRows}
          marketRowsLoading={marketRowsLoading}
          marketRowsError={marketRowsError}
        />
      </div>
    </div>
  )
}
