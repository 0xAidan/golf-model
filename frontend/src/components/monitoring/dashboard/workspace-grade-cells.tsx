import { resolvePastMatchupGrade } from "@/lib/matchup-pick-grade"
import { gradeSecondaryBetFromLeaderboard } from "@/lib/outright-replay-grade"
import type { FlattenedSecondaryBet, LiveLeaderboardRow, MatchupBet } from "@/lib/types"

import { PanelBackfill } from "../panel-backfill"

const AWAITING_RESULTS_TITLE = "Awaiting final results before this pick can be graded."

function AwaitingResultsLabel() {
  return (
    <span className="text-pending" title={AWAITING_RESULTS_TITLE} aria-label="Awaiting results">
      Awaiting results
    </span>
  )
}

function UngradedLabel({ title }: { title: string }) {
  return (
    <span className="text-pending" title={title} aria-label="Ungraded">
      Ungraded
    </span>
  )
}

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
    return <AwaitingResultsLabel />
  }
  if (g.kind === "ungraded") {
    return <UngradedLabel title={g.title} />
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
  completedReplay = false,
}: {
  bet: FlattenedSecondaryBet
  leaderboard: LiveLeaderboardRow[] | undefined
  completedReplay?: boolean
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
    if (completedReplay) {
      return <UngradedLabel title="No graded outcome stored for this pick yet. Use Grade event to reconcile it." />
    }
    return <AwaitingResultsLabel />
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
  if (completedReplay) {
    return <UngradedLabel title="No graded outcome stored for this pick yet. Use Grade event to reconcile it." />
  }
  return (
    <span
      className="num"
      title="Unsupported market for replay grading, or the player is still missing from the final leaderboard."
      aria-label="Unavailable"
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

export function WorkspaceLoadingState({ message }: { message: string }) {
  return (
    <PanelBackfill message={message} loading testId="workspace-loading-state" />
  )
}

export function WorkspaceErrorState({ message }: { message: string }) {
  return (
    <PanelBackfill message={message} loading={false} testId="workspace-error-state" />
  )
}
