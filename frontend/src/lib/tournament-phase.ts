/**
 * Tournament-week phase detection — "the site knows what day it is".
 * Derives build / track / review mode from the live-refresh snapshot
 * state (no new backend dependency): a live event => track, a completed
 * event with no live/upcoming => review, otherwise upcoming => build.
 */
import type { LiveRefreshSnapshot } from "@/lib/types"

export type TournamentPhase = "build" | "track" | "review"

export type PhaseInfo = {
  phase: TournamentPhase
  label: string
  accent: string
  blurb: string
}

const PHASES: Record<TournamentPhase, Omit<PhaseInfo, "phase">> = {
  build: {
    label: "Card building",
    accent: "var(--phase-build)",
    blurb: "Lines are posting for the weekend — assemble the card.",
  },
  track: {
    label: "Live tracking",
    accent: "var(--phase-track)",
    blurb: "Tournament in progress — watch movers and act on live edges.",
  },
  review: {
    label: "Review",
    accent: "var(--phase-review)",
    blurb: "Event wrapped — grade results and study model performance.",
  },
}

export function detectPhase(snapshot: LiveRefreshSnapshot | null | undefined): PhaseInfo {
  const hasLive = Boolean(snapshot?.live_tournament?.rankings?.length)
  const hasUpcoming = Boolean(snapshot?.upcoming_tournament?.rankings?.length)
  let phase: TournamentPhase
  if (hasLive) phase = "track"
  else if (!hasUpcoming) phase = "review"
  else phase = "build"

  return { phase, ...PHASES[phase] }
}
