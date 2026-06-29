import type { LiveLeaderboardRow, MatchupBet } from "@/lib/types"

export type PickGradeLetter = "W" | "L" | "P"

export type ResolvedPickGrade =
  | { kind: "letter"; letter: PickGradeLetter; title: string }
  | { kind: "pending"; title: string }
  | { kind: "ungraded"; title: string }
  | { kind: "dash"; title: string }

const CUT_LIKE = new Set(["CUT", "MC", "WD", "W/D", "DQ", "DFS", "MDF", "DNS"])

export function normalizePlayerKey(raw: string | undefined | null): string {
  return String(raw ?? "")
    .trim()
    .toLowerCase()
}

/** Parse stored JSON payload for an explicit graded outcome (never infer loss from absence). */
export function readStoredMatchupOutcome(payload: Record<string, unknown> | undefined): "win" | "loss" | "push" | null {
  if (!payload) return null
  const direct = payload.outcome ?? payload.graded_outcome ?? payload.pick_outcome
  if (direct === "win" || direct === "loss" || direct === "push") return direct
  if (payload.is_push === true) return "push"
  if (Number(payload.hit) === 1) return "win"
  return null
}

export function parseFinishRank(raw: string | undefined | null): number | null {
  if (!raw) return null
  const fin = String(raw).trim().toUpperCase()
  if (!fin || CUT_LIKE.has(fin)) return null
  const stripped = fin.startsWith("T") ? fin.slice(1) : fin
  const n = Number.parseInt(stripped, 10)
  return Number.isFinite(n) ? n : null
}

export function finishTextFromRow(row: LiveLeaderboardRow): string | null {
  const fs = row.finish_state != null && String(row.finish_state).trim() !== "" ? String(row.finish_state).trim() : null
  if (fs) return fs
  const pos = row.position != null && String(row.position).trim() !== "" ? String(row.position).trim() : null
  return pos
}

function buildFinishRankByPlayerKey(leaderboard: LiveLeaderboardRow[]): Map<string, number | null> {
  const map = new Map<string, number | null>()
  for (const row of leaderboard) {
    const text = finishTextFromRow(row)
    const rank = parseFinishRank(text)
    const keyFromId = normalizePlayerKey(row.player_key ?? "")
    const keyFromName = normalizePlayerKey(row.player)
    if (keyFromId) {
      map.set(keyFromId, rank)
    }
    if (keyFromName) {
      map.set(keyFromName, rank)
    }
  }
  return map
}

/** Resolve finish rank using stored key first, then display name (replay rows often mismatch DG keys). */
function lookupFinishRankForSide(
  ranks: Map<string, number | null>,
  key: string,
  display: string,
): number | null | undefined {
  const pk = normalizePlayerKey(key)
  if (pk && ranks.has(pk)) {
    return ranks.get(pk) ?? null
  }
  const pd = normalizePlayerKey(display)
  if (pd && ranks.has(pd)) {
    return ranks.get(pd) ?? null
  }
  return undefined
}

/**
 * Head-to-head tournament matchup grade from final-style leaderboard rows
 * (finish_state / position like "T5", "12", "CUT"). Mirrors src.scoring matchup branch
 * for integer ranks; both missing cut → push.
 */
export function gradeTournamentMatchupFromLeaderboard(
  matchup: Pick<MatchupBet, "pick_key" | "opponent_key" | "market_type" | "pick" | "opponent">,
  leaderboard: LiveLeaderboardRow[] | undefined | null,
): "win" | "loss" | "push" | null {
  if (!leaderboard || leaderboard.length === 0) return null

  const market = String(matchup.market_type ?? "tournament_matchups")
  if (market === "round_matchups") return null

  const ranks = buildFinishRankByPlayerKey(leaderboard)
  const pickRank = lookupFinishRankForSide(ranks, matchup.pick_key, matchup.pick)
  const oppRank = lookupFinishRankForSide(ranks, matchup.opponent_key, matchup.opponent)
  const missingPick = pickRank === undefined
  const missingOpp = oppRank === undefined
  if (missingPick || missingOpp) return null

  if (pickRank == null && oppRank == null) return "push"
  if (pickRank == null && oppRank != null) return "loss"
  if (pickRank != null && oppRank == null) return "win"
  if (pickRank != null && oppRank != null) {
    if (pickRank < oppRank) return "win"
    if (pickRank > oppRank) return "loss"
    return "push"
  }
  return null
}

export function resolvePastMatchupGrade(
  matchup: MatchupBet,
  leaderboard: LiveLeaderboardRow[] | undefined | null,
  options?: { completedReplay?: boolean },
): ResolvedPickGrade {
  const stored = matchup.graded_result ?? null
  if (stored === "win") return { kind: "letter", letter: "W", title: "Win" }
  if (stored === "loss") return { kind: "letter", letter: "L", title: "Loss" }
  if (stored === "push") return { kind: "letter", letter: "P", title: "Push" }

  const market = String(matchup.market_type ?? "tournament_matchups")
  if (market === "round_matchups") {
    return {
      kind: "dash",
      title: "Round matchup — final result is not derived in cockpit (no per-round board).",
    }
  }

  const fromBoard = gradeTournamentMatchupFromLeaderboard(matchup, leaderboard)
  if (fromBoard === "win") return { kind: "letter", letter: "W", title: "Win (lower finish beats higher)" }
  if (fromBoard === "loss") return { kind: "letter", letter: "L", title: "Loss" }
  if (fromBoard === "push") return { kind: "letter", letter: "P", title: "Push (tie or both missed cut)" }

  if (options?.completedReplay) {
    return {
      kind: "ungraded",
      title: "Not graded yet — use Grade event in the header after the tournament completes.",
    }
  }

  return {
    kind: "pending",
    title: "Pending — leaderboard does not yet show a definitive finish for both players.",
  }
}
