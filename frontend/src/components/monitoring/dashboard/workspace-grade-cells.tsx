import { resolvePastMatchupGrade } from "@/lib/matchup-pick-grade"
import { gradeSecondaryBetFromLeaderboard } from "@/lib/outright-replay-grade"
import type { FlattenedSecondaryBet, LiveLeaderboardRow, MatchupBet } from "@/lib/types"

import { PanelBackfill } from "../panel-backfill"

export function PastPickGradeCell({
  matchup,
  leaderboard,
  completedReplay = false,
}: {
  matchup: MatchupBet
  leaderboard: LiveLeaderboardRow[] | undefined
  completedReplay?: boolean
}) {
  const g = resolvePastMatchupGrade(matchup, leaderboard, { completedReplay })
  if (g.kind === "letter") {
    const cls = g.letter === "W" ? "win" : g.letter === "L" ? "loss" : "push"
    return (
      <span className={`pick-result-badge ${cls}`} title={g.title} aria-label={g.title}>
        {g.letter}
      </span>
    )
  }
  if (g.kind === "pending") {
    return (
      <span className="text-pending" title={g.title}>
        Pending
      </span>
    )
  }
  if (g.kind === "ungraded") {
    return (
      <span className="text-pending" title={g.title} aria-label={g.title}>
        Ungraded
      </span>
    )
  }
  return (
    <span className="num num-faint" title={g.title} aria-label={g.title}>
      —
    </span>
  )
}

export function PastSecondaryGradeCell({
  bet,
  leaderboard,
}: {
  bet: FlattenedSecondaryBet
  leaderboard: LiveLeaderboardRow[] | undefined
}) {
  if (bet.graded_result === "win") {
    return (
      <span className="pick-result-badge win" title="Win" aria-label="Win">
        W
      </span>
    )
  }
  if (bet.graded_result === "loss") {
    return (
      <span className="pick-result-badge loss" title="Loss" aria-label="Loss">
        L
      </span>
    )
  }
  if (bet.graded_result === "push") {
    return (
      <span className="pick-result-badge push" title="Push" aria-label="Push">
        P
      </span>
    )
  }

  if (!leaderboard || leaderboard.length === 0) {
    return (
      <span style={{ fontSize: 11, color: "var(--text-muted)" }} title="Waiting for final leaderboard">
        Pending
      </span>
    )
  }
  const graded = gradeSecondaryBetFromLeaderboard(bet, leaderboard)
  if (graded) {
    const letter = graded.outcome === "win" ? "W" : "L"
    const cls = graded.outcome === "win" ? "win" : "loss"
    let title = graded.outcome === "win" ? "Win" : "Loss"
    if (graded.outcome === "win" && graded.fraction > 0 && graded.fraction < 1) {
      title = `Dead heat: ${(graded.fraction * 100).toFixed(1)}% of stake wins`
    }
    return (
      <span className={`pick-result-badge ${cls}`} title={title} aria-label={title}>
        {letter}
      </span>
    )
  }
  return (
    <span
      className="num"
      style={{ color: "var(--text-faint)" }}
      title="Not graded — unsupported market (e.g. FRL) or player missing from leaderboard"
      aria-label="Not graded"
    >
      —
    </span>
  )
}

export function WorkspaceEmptyState({ message }: { message: string }) {
  return (
    <PanelBackfill message={message} loading={false} testId="workspace-empty-state" />
  )
}
