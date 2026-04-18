import { flattenSecondaryBets } from "@/lib/prediction-board"
import type { FlattenedSecondaryBet, MatchupBet, PastMarketPredictionRow, PredictionRunResponse } from "@/lib/types"

export function getRawGeneratedMatchups(predictionRun: PredictionRunResponse | null): MatchupBet[] {
  return predictionRun?.matchup_bets_all_books ?? predictionRun?.matchup_bets ?? []
}

export function getRawGeneratedSecondaryBets(predictionRun: PredictionRunResponse | null) {
  return flattenSecondaryBets(predictionRun)
}

export function buildReplayGeneratedMatchups(rows: PastMarketPredictionRow[]): MatchupBet[] {
  return rows
    .filter((row) => row.market_family === "matchup")
    .map((row) => {
      const payload = row.payload ?? {}
      const ev = typeof row.ev === "number" ? row.ev : Number(payload.ev ?? 0)
      const modelWinProb =
        typeof row.model_prob === "number"
          ? row.model_prob
          : typeof payload.model_win_prob === "number"
            ? payload.model_win_prob
            : 0.5
      const impliedProb =
        typeof row.implied_prob === "number"
          ? row.implied_prob
          : typeof payload.implied_prob === "number"
            ? payload.implied_prob
            : 0.5

      return {
        pick: row.player_display ?? "Unknown player",
        pick_key: row.player_key ?? "",
        opponent: row.opponent_display ?? "Unknown opponent",
        opponent_key: row.opponent_key ?? "",
        odds: row.odds ?? "--",
        book: row.book ?? undefined,
        model_win_prob: modelWinProb,
        implied_prob: impliedProb,
        ev,
        ev_pct: `${(ev * 100).toFixed(1)}%`,
        composite_gap: numberFromPayload(payload.composite_gap),
        form_gap: numberFromPayload(payload.form_gap),
        course_fit_gap: numberFromPayload(payload.course_fit_gap),
        reason: typeof payload.reason === "string" ? payload.reason : "Stored replay market row",
        tier: typeof payload.tier === "string" ? payload.tier : undefined,
        conviction: numberFromPayload(payload.conviction),
        pick_momentum: numberFromPayload(payload.pick_momentum),
        opp_momentum: numberFromPayload(payload.opp_momentum),
        momentum_aligned: typeof payload.momentum_aligned === "boolean" ? payload.momentum_aligned : undefined,
        market_type: row.market_type ?? undefined,
      }
    })
    .sort((left, right) => right.ev - left.ev)
}

export function buildReplayGeneratedSecondaryBets(rows: PastMarketPredictionRow[]): FlattenedSecondaryBet[] {
  return rows
    .filter((row) => row.market_family !== "matchup")
    .map((row) => ({
      market: row.market_type ?? row.market_family,
      player: row.player_display ?? "Unknown player",
      player_display: row.player_display ?? "Unknown player",
      player_key: row.player_key ?? undefined,
      odds: row.odds ?? "--",
      ev: typeof row.ev === "number" ? row.ev : 0,
      book: row.book ?? undefined,
    }))
    .sort((left, right) => right.ev - left.ev)
}

function numberFromPayload(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : 0
}
