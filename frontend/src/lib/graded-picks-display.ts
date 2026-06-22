import type { FlattenedSecondaryBet, MatchupBet, TrackRecordPick } from "@/lib/types"

const storedOutcomeFromPick = (pick: TrackRecordPick): "win" | "loss" | "push" | null => {
  if (pick.outcome === "win" || pick.outcome === "loss" || pick.outcome === "push") {
    return pick.outcome
  }
  if (Number(pick.hit ?? 0) === 1) return "win"
  if (Number(pick.profit ?? 0) === 0 && pick.hit === 0) return "push"
  if (pick.hit != null) return "loss"
  return null
}

const isPositiveEv = (pick: TrackRecordPick): boolean => Number(pick.ev ?? 0) > 0

export const gradedPicksToMatchups = (picks: TrackRecordPick[]): MatchupBet[] =>
  picks
    .filter((pick) => String(pick.bet_type ?? "").trim().toLowerCase() === "matchup")
    .filter(isPositiveEv)
    .map((pick) => {
      const ev = Number(pick.ev ?? 0)
      const gradedResult = storedOutcomeFromPick(pick)
      return {
        pick: pick.player_display,
        pick_key: pick.player_key ?? "",
        opponent: pick.opponent_display ?? "",
        opponent_key: pick.opponent_key ?? "",
        odds: pick.market_odds ?? "--",
        book: pick.market_book ?? undefined,
        model_win_prob: Number(pick.model_prob ?? 0.5),
        implied_prob: Number(pick.model_prob ?? 0.5),
        ev,
        ev_pct: `${(ev * 100).toFixed(1)}%`,
        composite_gap: 0,
        form_gap: 0,
        course_fit_gap: 0,
        reason: pick.reasoning ?? "Graded model pick",
        ...(gradedResult ? { graded_result: gradedResult } : {}),
      }
    })
    .sort((left, right) => right.ev - left.ev)

export const gradedPicksToSecondaryBets = (picks: TrackRecordPick[]): FlattenedSecondaryBet[] =>
  picks
    .filter((pick) => String(pick.bet_type ?? "").trim().toLowerCase() !== "matchup")
    .filter(isPositiveEv)
    .map((pick) => ({
      market: String(pick.bet_type ?? "outright").trim().toLowerCase(),
      player: pick.player_display,
      player_display: pick.player_display,
      player_key: pick.player_key,
      odds: pick.market_odds ?? "--",
      ev: Number(pick.ev ?? 0),
      book: pick.market_book ?? undefined,
    }))
    .sort((left, right) => right.ev - left.ev)
