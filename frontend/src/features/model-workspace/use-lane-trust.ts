import type { PredictionRunResponse } from "@/lib/types"

export type LaneTrustState = {
  tone: "healthy" | "warn" | "danger" | "neutral"
  title?: string
  message: string
}

export const buildLaneTrustState = ({
  snapshotNotice,
  displayPredictionRun,
  diagnosticsState,
  usingProdSnapshotFallback,
  labLanePartialSections,
}: {
  snapshotNotice: string | null
  displayPredictionRun: PredictionRunResponse | null
  diagnosticsState?: string
  usingProdSnapshotFallback?: boolean
  labLanePartialSections?: boolean
}): LaneTrustState | null => {
  if (usingProdSnapshotFallback) {
    return {
      tone: "warn",
      title: "Lab lane off",
      message:
        "Boards mirror the main snapshot until the server enables the lab profile and recomputes lab sections.",
    }
  }
  if (labLanePartialSections) {
    return {
      tone: "warn",
      title: "Partial lab snapshot",
      message:
        "Only one lab section is populated — the missing side still uses the production board until both fill.",
    }
  }
  if (snapshotNotice) {
    return {
      tone: "danger",
      title: "Snapshot notice",
      message: snapshotNotice,
    }
  }
  if (
    displayPredictionRun?.hydration_section === "upcoming_fallback_live" ||
    displayPredictionRun?.hydration_section === "live_fallback_upcoming"
  ) {
    return {
      tone: "warn",
      title: "Section fallback",
      message:
        displayPredictionRun.hydration_section === "upcoming_fallback_live"
          ? "Upcoming view is showing live snapshot data — upcoming section unavailable."
          : "Live view is showing upcoming snapshot data — live section unavailable.",
    }
  }
  if (diagnosticsState === "team_event") {
    return {
      tone: "warn",
      title: "Team event",
      message: "Matchup picks are withheld for team-format events.",
    }
  }
  if (diagnosticsState === "no_market") {
    return {
      tone: "neutral",
      title: "No market",
      message: "Books have not posted markets for this event yet.",
    }
  }
  if (diagnosticsState === "no_edges") {
    return {
      tone: "neutral",
      title: "No +EV edges",
      message: "Markets are posted but no plays cleared the model gates.",
    }
  }
  return null
}
