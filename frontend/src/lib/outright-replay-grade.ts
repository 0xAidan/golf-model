import {
  finishTextFromRow,
  normalizePlayerKey,
  parseFinishRank,
} from "@/lib/matchup-pick-grade"
import type { FlattenedSecondaryBet, LiveLeaderboardRow } from "@/lib/types"

const CUT_LIKE = new Set(["CUT", "MC", "WD", "W/D", "DQ", "DFS", "MDF", "DNS"])

/** Mirrors src.scoring.MARKET_THRESHOLDS — null means special make_cut handling. */
const MARKET_THRESHOLDS: Record<string, number | null> = {
  outright: 1,
  win: 1,
  frl: 1,
  top5: 5,
  top_5: 5,
  top10: 10,
  top_10: 10,
  top20: 20,
  top_20: 20,
  make_cut: null,
}

export function normalizeSecondaryBetType(market: string): string | null {
  const raw = market.trim().toLowerCase()
  if (!raw || raw.includes("matchup")) {
    return null
  }
  const compact = raw.replace(/\s+/g, "_").replace(/-+/g, "_")
  if (compact === "frl" || (raw.includes("first") && raw.includes("round"))) {
    return null
  }
  if (Object.prototype.hasOwnProperty.call(MARKET_THRESHOLDS, compact)) {
    return compact
  }
  if (raw.includes("make") && raw.includes("cut")) {
    return "make_cut"
  }
  if ((raw.includes("top") || raw.includes("finish")) && raw.includes("20")) {
    return "top20"
  }
  if ((raw.includes("top") || raw.includes("finish")) && raw.includes("10")) {
    return "top10"
  }
  if ((raw.includes("top") || raw.includes("finish")) && raw.includes("5")) {
    return "top5"
  }
  if (raw.includes("outright") || raw === "winner") {
    return "outright"
  }
  return null
}

type ResultRow = { finish_position: number | null; finish_text: string }

function buildAllResults(leaderboard: LiveLeaderboardRow[]): ResultRow[] {
  return leaderboard.map((row) => {
    const text = finishTextFromRow(row)
    return {
      finish_position: parseFinishRank(text),
      finish_text: text ?? "",
    }
  })
}

function countTiedAtPosition(finishPos: number | null, allResults: ResultRow[]): number {
  if (finishPos === null) {
    return 0
  }
  let count = 0
  for (const r of allResults) {
    const rPos = r.finish_position
    const rText = r.finish_text.trim().toUpperCase()
    if (rPos === finishPos && rText.startsWith("T")) {
      count += 1
    }
  }
  return count === 0 ? 1 : count
}

function deadHeatFraction(finishPos: number | null, threshold: number, numTied: number): number {
  if (numTied <= 0 || finishPos === null) {
    return 1
  }
  const remainingSpots = threshold - (finishPos - 1)
  if (remainingSpots <= 0) {
    return 0
  }
  if (remainingSpots >= numTied) {
    return 1
  }
  return remainingSpots / numTied
}

function rowMadeCut(row: LiveLeaderboardRow): boolean {
  const text = finishTextFromRow(row)
  if (!text) {
    return false
  }
  return !CUT_LIKE.has(text.trim().toUpperCase())
}

function findLeaderboardRowForBet(
  bet: FlattenedSecondaryBet,
  leaderboard: LiveLeaderboardRow[],
): LiveLeaderboardRow | undefined {
  const pk = normalizePlayerKey(bet.player_key ?? "")
  const pd = normalizePlayerKey(bet.player_display ?? bet.player)
  for (const row of leaderboard) {
    const rk = normalizePlayerKey(row.player_key ?? "")
    const rn = normalizePlayerKey(row.player)
    if (pk && (rk === pk || rn === pk)) {
      return row
    }
    if (pd && (rk === pd || rn === pd)) {
      return row
    }
  }
  return undefined
}

function determineOutcome(
  betType: string,
  finishPosition: number | null,
  finishText: string | null,
  madeCut: boolean,
  allResults: ResultRow[],
): { hit: number; fraction: number } {
  const result = { hit: 0, fraction: 0 }
  const bt = betType.toLowerCase().trim()

  if (bt === "make_cut") {
    if (madeCut) {
      result.hit = 1
      result.fraction = 1
    }
    return result
  }

  const threshold = MARKET_THRESHOLDS[bt]
  if (threshold === undefined) {
    return result
  }
  if (threshold === null) {
    return result
  }

  if (finishPosition === null) {
    return result
  }

  if (finishPosition > threshold) {
    return result
  }

  if (finishPosition < threshold) {
    result.hit = 1
    result.fraction = 1
    return result
  }

  const finUpper = String(finishText ?? "").trim().toUpperCase()
  const isTied = finUpper.startsWith("T")
  if (!isTied) {
    result.hit = 1
    result.fraction = 1
    return result
  }

  const numTied = countTiedAtPosition(finishPosition, allResults)
  const fraction = deadHeatFraction(finishPosition, threshold, numTied)
  if (fraction > 0) {
    result.hit = 1
    result.fraction = Number(fraction.toFixed(6))
  }
  return result
}

function americanToDecimalOdds(american: string): number | null {
  const raw = Number.parseInt(String(american).replace("+", ""), 10)
  if (!Number.isFinite(raw) || raw === 0) {
    return null
  }
  if (raw > 0) {
    return raw / 100 + 1
  }
  return 100 / Math.abs(raw) + 1
}

/** Profit for 1 unit stake; mirrors src.scoring.compute_profit (non-push). */
export function computeReplayProfitUnits(
  hit: boolean,
  fraction: number,
  americanOdds: string,
): number | null {
  const oddsDecimal = americanToDecimalOdds(americanOdds)
  if (oddsDecimal === null) {
    return null
  }
  if (!hit || fraction <= 0) {
    return -1
  }
  if (fraction >= 1) {
    return oddsDecimal - 1
  }
  return fraction * (oddsDecimal - 1) - (1 - fraction)
}

export type OutrightReplayGrade = {
  outcome: "win" | "loss"
  profit: number
  fraction: number
}

/**
 * Grade a non-matchup market row against the final leaderboard (past replay KPIs).
 * Returns null when the market type is unknown or the player cannot be placed on the board.
 */
export function gradeSecondaryBetFromLeaderboard(
  bet: FlattenedSecondaryBet,
  leaderboard: LiveLeaderboardRow[] | undefined | null,
): OutrightReplayGrade | null {
  if (!leaderboard || leaderboard.length === 0) {
    return null
  }
  const bt = normalizeSecondaryBetType(bet.market)
  if (!bt || bt === "matchup") {
    return null
  }

  const row = findLeaderboardRowForBet(bet, leaderboard)
  if (!row) {
    return null
  }

  const finishText = finishTextFromRow(row)
  const finishPosition = parseFinishRank(finishText)
  const madeCut = rowMadeCut(row)
  const allResults = buildAllResults(leaderboard)

  const outcome = determineOutcome(bt, finishPosition, finishText, madeCut, allResults)
  const profit = computeReplayProfitUnits(Boolean(outcome.hit), outcome.fraction, bet.odds)
  if (profit === null) {
    return null
  }

  return {
    outcome: outcome.hit ? "win" : "loss",
    profit,
    fraction: outcome.fraction,
  }
}
