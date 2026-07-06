import { useQuery } from "@tanstack/react-query"

import { useOpsHealth } from "@/hooks/use-ops-health"
import { api } from "@/lib/api"
import { formatDateTime } from "@/lib/format"

type OpsJobSummary = {
  id: string
  status: string
  progress_pct: number
  message?: string
  error?: string
  updated_at?: string
}

export function OpsHealthPanel() {
  const healthQuery = useOpsHealth()
  const gradeJobQuery = useQuery({
    queryKey: ["ops-job-latest-grade"],
    queryFn: () => api.getLatestOpsJob("grade") as Promise<{ job: OpsJobSummary | null }>,
    refetchInterval: 5_000,
  })

  const grading = healthQuery.data?.grading ?? {}
  const worker = healthQuery.data?.live_refresh ?? {}
  const gradeJob = gradeJobQuery.data?.job

  return (
    <div className="space-y-3 text-sm" data-testid="ops-health-panel">
      <p>
        <strong>Worker:</strong>{" "}
        {worker.running
          ? "Running"
          : "Stopped — open Dashboard and click Refresh, or wait for the scheduled worker to restart."}
      </p>
      {worker.last_recompute_at ? (
        <p className="text-[var(--text-secondary)]">
          Last snapshot recompute: {formatDateTime(String(worker.last_recompute_at))}
        </p>
      ) : null}
      <p>
        <strong>Grading:</strong> {String(grading.status ?? "unknown")}
        {grading.reconciliation?.status ? ` · reconciliation ${grading.reconciliation.status}` : ""}
      </p>
      {grading.last_auto_grade_at ? (
        <p className="text-[var(--text-secondary)]">
          Last auto-grade: {formatDateTime(String(grading.last_auto_grade_at))} (
          {String(grading.last_auto_grade_status ?? "")})
        </p>
      ) : null}
      {gradeJob ? (
        <p data-testid="ops-latest-grade-job">
          <strong>Latest grade job:</strong> {gradeJob.status}
          {gradeJob.progress_pct > 0 && gradeJob.progress_pct < 100 ? ` · ${gradeJob.progress_pct}%` : ""}
          {gradeJob.message ? ` — ${gradeJob.message}` : ""}
          {gradeJob.error ? ` (${gradeJob.error})` : ""}
        </p>
      ) : (
        <p className="text-[var(--text-tertiary)]">No grade jobs recorded yet.</p>
      )}
      <p className="text-[var(--text-tertiary)]">
        Routine recovery stays in the app — you should not need SSH for refresh or grading.
      </p>
    </div>
  )
}
