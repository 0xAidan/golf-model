import { gradeTournamentMatchupFromLeaderboard } from "@/lib/matchup-pick-grade"
import { gradeSecondaryBetFromLeaderboard } from "@/lib/outright-replay-grade"
import type {
  FlattenedSecondaryBet,
  GradedTournamentSummary,
  LiveLeaderboardRow,
  MatchupBet,
  RecordBucket,
  RecordSummary,
} from "@/lib/types"

const EMPTY_BUCKET: RecordBucket = {
  picks: 0,
  wins: 0,
  losses: 0,
  pushes: 0,
  profit: 0,
  hit_rate: null,
}

const makeBucket = (): RecordBucket => ({ ...EMPTY_BUCKET })

const finalizeBucket = (bucket: RecordBucket): RecordBucket => ({
  ...bucket,
  profit: Number(bucket.profit.toFixed(2)),
  hit_rate: bucket.picks > 0 ? Number((bucket.wins / bucket.picks).toFixed(3)) : null,
})

const marketBucketForBetType = (betType?: string | null): "matchups" | "outrights" => {
  if (betType?.trim().toLowerCase() === "matchup") return "matchups"
  return "outrights"
}

const emptySummary = (): RecordSummary => ({
  outrights: makeBucket(),
  matchups: makeBucket(),
  combined: makeBucket(),
})

const normalizeBucket = (bucket?: RecordBucket): RecordBucket => {
  if (!bucket) return makeBucket()
  return {
    picks: Number(bucket.picks ?? 0),
    wins: Number(bucket.wins ?? 0),
    losses: Number(bucket.losses ?? 0),
    pushes: Number(bucket.pushes ?? 0),
    profit: Number(bucket.profit ?? 0),
    hit_rate: bucket.hit_rate ?? null,
  }
}

export type DisplayRecordBucket = RecordBucket & {
  recordLabel: string
  hitRateLabel: string
}

export type DisplayRecordSummary = {
  outrights: DisplayRecordBucket
  matchups: DisplayRecordBucket
  combined: DisplayRecordBucket
}

const toDisplayBucket = (bucket: RecordBucket): DisplayRecordBucket => ({
  ...bucket,
  recordLabel: `${bucket.wins}-${bucket.losses}-${bucket.pushes}`,
  hitRateLabel: bucket.hit_rate === null ? "—" : `${Math.round(bucket.hit_rate * 100)}%`,
})

export const buildGradingRecordSummary = (
  gradingHistory: GradedTournamentSummary[],
  apiSummary?: RecordSummary,
): DisplayRecordSummary => {
  const summary = apiSummary
    ? {
        outrights: normalizeBucket(apiSummary.outrights),
        matchups: normalizeBucket(apiSummary.matchups),
        combined: normalizeBucket(apiSummary.combined),
      }
    : gradingHistory.reduce<RecordSummary>((accumulator, event) => {
        for (const pick of event.picks ?? []) {
          const bucketName = marketBucketForBetType(pick.bet_type)
          const profit = Number(pick.profit ?? 0)
          const isWin = Number(pick.hit ?? 0) === 1
          const isPush = !isWin && profit === 0

          for (const bucket of [accumulator[bucketName], accumulator.combined]) {
            bucket.picks += 1
            bucket.profit += profit
            if (isWin) {
              bucket.wins += 1
            } else if (isPush) {
              bucket.pushes += 1
            } else {
              bucket.losses += 1
            }
          }
        }
        return accumulator
      }, emptySummary())

  return {
    outrights: toDisplayBucket(finalizeBucket(summary.outrights)),
    matchups: toDisplayBucket(finalizeBucket(summary.matchups)),
    combined: toDisplayBucket(finalizeBucket(summary.combined)),
  }
}

const americanOddsProfit = (odds: string | number | undefined | null) => {
  const raw = typeof odds === "number" ? odds : Number.parseInt(String(odds ?? "").replace("+", ""), 10)
  if (!Number.isFinite(raw) || raw === 0) return 0
  if (raw > 0) return raw / 100
  return 100 / Math.abs(raw)
}

export const buildPastReplayRecordSummary = (
  matchups: MatchupBet[],
  outrights: FlattenedSecondaryBet[],
  leaderboardRows: LiveLeaderboardRow[],
): DisplayRecordSummary => {
  const summary = emptySummary()

  const applyBucket = (bucket: RecordBucket, outcome: "win" | "loss" | "push", profit: number) => {
    bucket.picks += 1
    bucket.profit += profit
    if (outcome === "win") {
      bucket.wins += 1
    } else if (outcome === "push") {
      bucket.pushes += 1
    } else {
      bucket.losses += 1
    }
  }

  for (const matchup of matchups) {
    const outcome =
      matchup.graded_result ??
      gradeTournamentMatchupFromLeaderboard(matchup, leaderboardRows)
    if (outcome !== "win" && outcome !== "loss" && outcome !== "push") {
      continue
    }

    const profit =
      outcome === "win"
        ? americanOddsProfit(matchup.odds)
        : outcome === "loss"
          ? -1
          : 0

    applyBucket(summary.matchups, outcome, profit)
    applyBucket(summary.combined, outcome, profit)
  }

  for (const bet of outrights) {
    const graded = gradeSecondaryBetFromLeaderboard(bet, leaderboardRows)
    if (!graded) {
      continue
    }

    const outcomeLetter = graded.outcome === "win" ? "win" : "loss"
    applyBucket(summary.outrights, outcomeLetter, graded.profit)
    applyBucket(summary.combined, outcomeLetter, graded.profit)
  }

  return {
    outrights: toDisplayBucket(finalizeBucket(summary.outrights)),
    matchups: toDisplayBucket(finalizeBucket(summary.matchups)),
    combined: toDisplayBucket(finalizeBucket(summary.combined)),
  }
}
