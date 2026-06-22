import type { MatchupBet, TrackRecordPick } from "@/lib/types"

const normalizeKey = (value: string | undefined | null): string =>
  String(value ?? "")
    .trim()
    .toLowerCase()

const matchupPickKey = (pick: TrackRecordPick): string =>
  [
    normalizeKey(pick.bet_type ?? "matchup"),
    normalizeKey(pick.player_key ?? pick.player_display),
    normalizeKey(pick.opponent_key ?? pick.opponent_display),
  ].join("|")

const storedOutcomeFromPick = (pick: TrackRecordPick): "win" | "loss" | "push" | null => {
  if (pick.outcome === "win" || pick.outcome === "loss" || pick.outcome === "push") {
    return pick.outcome
  }
  if (Number(pick.hit ?? 0) === 1) return "win"
  if (Number(pick.profit ?? 0) === 0 && pick.hit === 0) return "push"
  if (pick.hit != null) return "loss"
  return null
}

export const applyGradedPicksToMatchups = (
  matchups: MatchupBet[],
  gradedPicks: TrackRecordPick[] | undefined | null,
): MatchupBet[] => {
  if (!gradedPicks?.length) return matchups

  const gradedByKey = new Map<string, TrackRecordPick>()
  for (const pick of gradedPicks) {
    if (String(pick.bet_type ?? "").trim().toLowerCase() !== "matchup") continue
    gradedByKey.set(matchupPickKey(pick), pick)
  }

  return matchups.map((matchup) => {
    if (matchup.graded_result) return matchup
    const graded = gradedByKey.get(
      [
        "matchup",
        normalizeKey(matchup.pick_key ?? matchup.pick),
        normalizeKey(matchup.opponent_key ?? matchup.opponent),
      ].join("|"),
    )
    const stored = graded ? storedOutcomeFromPick(graded) : null
    if (!stored) return matchup
    return { ...matchup, graded_result: stored }
  })
}
