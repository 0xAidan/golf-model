import { useQuery } from "@tanstack/react-query"

import { api } from "@/lib/api"

export type OpsHealthResponse = {
  ok?: boolean
  summary?: string
  grading?: {
    status?: string
    events_with_ungraded_positive_ev?: number
    last_auto_grade_at?: string
    last_auto_grade_status?: string
    reconciliation?: { status?: string }
  }
  live_refresh?: {
    running?: boolean
    last_recompute_at?: string
    heartbeat_age_seconds?: number
    snapshot_age_seconds?: number
  }
  disk?: {
    status?: string
    free_mb?: number
    warn_mb?: number
    hard_mb?: number
  }
}

const OPS_HEALTH_QUERY_KEY = ["ops-health"] as const

export function useOpsHealth(pollMs = 30_000) {
  return useQuery({
    queryKey: OPS_HEALTH_QUERY_KEY,
    queryFn: () => api.getOpsHealth() as Promise<OpsHealthResponse>,
    refetchInterval: pollMs,
    staleTime: 10_000,
  })
}

export function opsHealthSeverity(data: OpsHealthResponse | undefined): "good" | "warn" | "bad" {
  if (!data) return "warn"
  if (data.ok === false) return "bad"
  if (data.disk?.status === "hard" || data.disk?.status === "warn") return "warn"
  if ((data.grading?.events_with_ungraded_positive_ev ?? 0) > 0) return "warn"
  return "good"
}
