/**
 * Lab sandbox picks — same tables as /matchups but fed from ``lab_*`` snapshot sections
 * and logs to ``picks`` with ``source=lab_sandbox`` via POST /api/lab/log-displayed-picks.
 */
import { useMutation } from "@tanstack/react-query"
import { useEffect, useMemo, useRef, useState } from "react"

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

const buildMatchupsPayload = (matchups: MatchupBet[]) =>
  matchups.map((m) => ({
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

const buildLabLogBody = (
  tournamentId: number,
  profileName: string,
  predictionRun: PredictionRunResponse | null,
  matchups: MatchupBet[],
  matchupDiagnostics?: MatchupDiagnostics,
) => ({
  tournament_id: tournamentId,
  profile_name: profileName,
  composite_results: predictionRun?.composite_results ?? [],
  matchups: buildMatchupsPayload(matchups),
  value_bets: predictionRun?.value_bets ?? {},
  matchup_failed_candidates: matchupDiagnostics?.failed_candidates ?? [],
})

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
  const lastSyncedFingerprint = useRef<string>("")

  const valueBetsSignature = useMemo(() => {
    const vb = predictionRun?.value_bets
    if (!vb || typeof vb !== "object") return ""
    return Object.keys(vb)
      .sort()
      .map((k) => {
        const rows = vb[k]
        return `${k}:${Array.isArray(rows) ? rows.length : 0}`
      })
      .join(",")
  }, [predictionRun?.value_bets])

  const picksLogFingerprint = useMemo(() => {
    if (tournamentId === null || tournamentId === undefined || !matchups.length) return ""
    const matchupSig = matchups
      .map((row) =>
        [row.pick_key, row.opponent_key, row.book, String(row.odds ?? ""), String(row.ev ?? "")].join(":"),
      )
      .sort()
      .join("|")
    return `${tournamentId}:${matchupSig}:${valueBetsSignature}`
  }, [tournamentId, matchups, valueBetsSignature])

  const logMutation = useMutation({
    mutationFn: () => {
      if (tournamentId === null || tournamentId === undefined) {
        throw new Error("Missing tournament_id for lab picks logging.")
      }
      return api.postLabLogDisplayedPicks(
        buildLabLogBody(tournamentId, profileName, predictionRun, matchups, matchupDiagnostics),
      )
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

  useEffect(() => {
    if (!picksLogFingerprint) return
    if (tournamentId === null || tournamentId === undefined) return
    if (!matchups.length) return
    if (picksLogFingerprint === lastSyncedFingerprint.current) return

    const timer = window.setTimeout(() => {
      void (async () => {
        try {
          const res = await api.postLabLogDisplayedPicks(
            buildLabLogBody(tournamentId, profileName, predictionRun, matchups, matchupDiagnostics),
          )
          if (res.ok) {
            lastSyncedFingerprint.current = picksLogFingerprint
          }
        } catch {
          // Network or server error — operator can use the manual button; avoid tight retry loops.
        }
      })()
    }, 2000)

    return () => window.clearTimeout(timer)
  }, [
    picksLogFingerprint,
    tournamentId,
    profileName,
    predictionRun,
    matchups,
    matchupDiagnostics,
  ])

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
        <strong>Lab picks</strong> — uses the parallel lab snapshot lane. Displayed matchups and value markets sync to
        the database automatically (deduped); <code style={{ fontSize: 11 }}>source=lab_sandbox</code>. Production{" "}
        <strong>/matchups</strong> is unchanged.
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
          {logMutation.isPending ? "Logging…" : "Log displayed lab picks now"}
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
