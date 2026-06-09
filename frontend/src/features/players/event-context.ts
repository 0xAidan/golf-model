import type { PredictionTab } from "@/hooks/use-prediction-tab"
import type { LiveRefreshSnapshot } from "@/lib/types"

export const resolvePlayersEventContext = ({
  liveSnapshot,
  predictionTab,
}: {
  liveSnapshot: LiveRefreshSnapshot | null
  predictionTab: PredictionTab
}) => {
  if (predictionTab === "past") {
    return {
      eventName: "Past events",
      courseName: undefined as string | undefined,
      fieldSize: 0,
      hasEvent: false,
    }
  }

  const section =
    predictionTab === "upcoming"
      ? liveSnapshot?.upcoming_tournament
      : liveSnapshot?.live_tournament

  return {
    eventName: section?.event_name ?? "No active event",
    courseName: section?.course_name ?? undefined,
    fieldSize: section?.field_size ?? 0,
    hasEvent: Boolean(section),
  }
}

export const formatSnapshotAge = (ageSeconds: number | null): string => {
  if (ageSeconds === null || ageSeconds === undefined) return "Waiting for snapshot"
  if (ageSeconds < 60) return `${ageSeconds}s ago`
  return `${Math.round(ageSeconds / 60)}m ago`
}
