import type { TrustTone } from "@/components/product/trust-status-banner"
import type { LiveRefreshSnapshot } from "@/lib/types"
import type { PredictionTab } from "@/hooks/use-prediction-tab"

export type PlayersTrustState = {
  tone: TrustTone
  title?: string
  message: string
} | null

export const buildPlayersTrustState = ({
  snapshotNotice,
  liveSnapshot,
  predictionTab,
}: {
  snapshotNotice: string | null
  liveSnapshot: LiveRefreshSnapshot | null
  predictionTab: PredictionTab
}): PlayersTrustState => {
  if (snapshotNotice) {
    return {
      tone: "danger",
      title: "Snapshot notice",
      message: snapshotNotice,
    }
  }

  if (predictionTab === "past") {
    return {
      tone: "neutral",
      title: "Past mode",
      message: "Switch to Live or Upcoming on the Dashboard for current field context.",
    }
  }

  const section =
    predictionTab === "upcoming"
      ? liveSnapshot?.upcoming_tournament
      : liveSnapshot?.live_tournament

  if (!section) {
    return {
      tone: "neutral",
      title: "No active event",
      message: "Showing DB + DataGolf profile only — no tournament model context loaded.",
    }
  }

  const diagnostics = section.diagnostics
  if (diagnostics?.state === "stale" || diagnostics?.state === "degraded") {
    const operatorMessage =
      diagnostics && "operator_message" in diagnostics
        ? String((diagnostics as { operator_message?: string }).operator_message ?? "")
        : ""
    return {
      tone: "warn",
      title: "Data freshness",
      message: operatorMessage || "Snapshot may be stale — verify before acting on picks.",
    }
  }

  return null
}
