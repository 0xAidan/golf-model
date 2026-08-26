import { Link } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { DataHealthPanel } from "@/components/data-health-panel"
import { DiagnosticsGradingPanel } from "@/components/cockpit/event-modules"
import { SystemStatusPanel } from "@/components/system/system-status-panel"
import { Button } from "@/components/ui/button"
import { CollapsibleSection } from "@/components/ui/collapsible-section"
import { TerminalPageHeader } from "@/components/ui/terminal-page-header"
import { useOpsHealth } from "@/hooks/use-ops-health"
import { api } from "@/lib/api"
import { buildDiagnosticsModel } from "@/lib/cockpit-event-models"
import { formatDateTime } from "@/lib/format"
import { formatAutoGradeStatusLabel } from "@/lib/grading-trust"
import type {
  DataHealthReport,
  DashboardState,
  FlattenedSecondaryBet,
  GradedTournamentSummary,
  LiveRefreshSnapshot,
  PredictionRunResponse,
} from "@/lib/types"
import type { PredictionTab } from "@/hooks/use-prediction-tab"

function formatAge(seconds?: number | null): string {
  if (seconds == null) return "unknown"
  if (seconds < 60) return `${seconds}s`
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`
  return `${(seconds / 3600).toFixed(1)}h`
}

function storageTone(report?: DataHealthReport): "good" | "warn" | "bad" {
  if (report?.status === "red") return "bad"
  if (report?.status === "yellow" || (report?.storage_warnings?.length ?? 0) > 0) return "warn"
  return "good"
}

function jobTone(status?: string): "good" | "warn" | "bad" {
  const normalized = String(status ?? "").toLowerCase()
  if (normalized === "error" || normalized === "failed") return "bad"
  if (normalized === "running" || normalized === "pending") return "warn"
  return "good"
}

export function SystemPage({
  dashboard,
  liveSnapshot,
  predictionTab,
  isLiveActive,
  gradingHistory,
  predictionRun,
  secondaryBets,
}: {
  dashboard?: DashboardState
  liveSnapshot: LiveRefreshSnapshot | null
  predictionTab: PredictionTab
  isLiveActive: boolean
  gradingHistory: GradedTournamentSummary[]
  predictionRun: PredictionRunResponse | null
  secondaryBets: FlattenedSecondaryBet[]
}) {
  const activeSection =
    predictionTab === "upcoming"
      ? liveSnapshot?.upcoming_tournament
      : liveSnapshot?.live_tournament

  const diagnosticsModel = buildDiagnosticsModel({
    mode: predictionTab,
    diagnostics: predictionTab === "past" ? undefined : activeSection?.diagnostics,
    dashboardAiAvailable: dashboard ? Boolean(dashboard.ai_status?.available) : undefined,
    strategySource: dashboard?.baseline_provenance?.strategy_source,
    strategyName: dashboard?.baseline_provenance?.live_strategy_name,
    warnings: predictionRun?.warnings,
    gradingHistory,
    selectedEventId: undefined,
    timelinePoints: [],
    currentSecondaryBets: secondaryBets,
  })

  const queryClient = useQueryClient()
  const opsHealthQuery = useOpsHealth()
  const dataHealthQuery = useQuery({
    queryKey: ["data-health", 2026],
    queryFn: () => api.getDataHealth(2026),
    staleTime: 60_000,
  })
  const latestGradeJobQuery = useQuery({
    queryKey: ["ops-job-latest-grade"],
    queryFn: () => api.getLatestOpsJob("grade"),
    refetchInterval: 5_000,
  })
  const restartWorker = useMutation({
    mutationFn: () => api.requestWorkerRestart({ requested_by: "system-page" }),
    onSuccess: (result) => {
      toast.message(result.message ?? "Worker restart requested.")
      void queryClient.invalidateQueries({ queryKey: ["ops-health"] })
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : "Worker restart request failed.")
    },
  })
  const gradeLeftover = useMutation({
    mutationFn: () =>
      api.startGradeJob({
        event_id: opsHealthQuery.data?.grading?.leftover_event_id ?? undefined,
        year: opsHealthQuery.data?.grading?.leftover_event_year ?? undefined,
        event_name: opsHealthQuery.data?.grading?.leftover_event_name ?? undefined,
      }),
    onSuccess: (result) => {
      toast.message(result.message ?? "Grade job started for the leftover event.")
      void queryClient.invalidateQueries({ queryKey: ["ops-health"] })
      void queryClient.invalidateQueries({ queryKey: ["ops-job-latest-grade"] })
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : "Grade leftover request failed.")
    },
  })

  const opsHealth = opsHealthQuery.data
  const dataHealth = dataHealthQuery.data
  const latestGradeJob = latestGradeJobQuery.data?.job
  const opsPending = opsHealthQuery.isPending && !opsHealth
  const dataHealthPending = dataHealthQuery.isPending && !dataHealth
  const jobsPending = latestGradeJobQuery.isPending && latestGradeJobQuery.data === undefined

  const workerRunning = opsHealth?.live_refresh?.running ?? false
  const workerTone: "good" | "warn" | "bad" = opsPending
    ? "warn"
    : workerRunning
      ? "good"
      : "bad"
  const gradingGap = opsHealth?.grading?.events_with_ungraded_positive_ev ?? 0
  const gradingTone: "good" | "warn" | "bad" = opsPending
    ? "warn"
    : gradingGap > 0
      ? "bad"
      : "good"
  const storagePanelTone: "good" | "warn" | "bad" = dataHealthPending
    ? "warn"
    : storageTone(dataHealth)
  const jobsPanelTone: "good" | "warn" | "bad" = jobsPending
    ? "warn"
    : jobTone(latestGradeJob?.status)

  const workerSummary = opsPending
    ? "Checking live refresh worker status…"
    : workerRunning
      ? "The live refresh worker is running."
      : "The live refresh worker is down, so fresh boards and auto-recovery are at risk."
  const heartbeatAgeSeconds =
    opsHealth?.live_refresh?.heartbeat_age_seconds ?? opsHealth?.heartbeat_age_seconds ?? null
  const workerDetail = opsPending
    ? "Waiting for ops health…"
    : [
        `Heartbeat age ${formatAge(heartbeatAgeSeconds)}`,
        `snapshot age ${formatAge(opsHealth?.live_refresh?.snapshot_age_seconds ?? null)}`,
        opsHealth?.worker_restart_request?.requested_at
          ? `restart requested by ${opsHealth.worker_restart_request.requested_by ?? "operator"}`
          : null,
      ]
        .filter(Boolean)
        .join(" · ")

  const leftoverEventName = opsHealth?.grading?.leftover_event_name?.trim()
  const gradingSummary = opsPending
    ? "Checking grading reconciliation…"
    : gradingGap > 0
      ? leftoverEventName && gradingGap === 1
        ? `${leftoverEventName} still has ungraded +EV picks.`
        : `${gradingGap} completed event${gradingGap === 1 ? "" : "s"} still ${
            gradingGap === 1 ? "has" : "have"
          } ungraded +EV picks.`
      : "Grading reconciliation is clear."
  const autoGradeLabel = formatAutoGradeStatusLabel(opsHealth?.grading?.last_auto_grade_status)
  const lastAutoGradeAt = opsHealth?.grading?.last_auto_grade_at
    ? formatDateTime(opsHealth.grading.last_auto_grade_at)
    : null
  const gradingDetail = opsPending
    ? "Waiting for ops health…"
    : [
        `Status ${opsHealth?.grading?.status ?? "unknown"}`,
        lastAutoGradeAt ? `last auto-grade ${lastAutoGradeAt}` : null,
        autoGradeLabel ? autoGradeLabel : null,
      ]
        .filter(Boolean)
        .join(" · ")

  const storageSummary = dataHealthPending
    ? "Checking storage and backups…"
    : storagePanelTone === "bad"
      ? "Storage health is in a red state and needs operator attention."
      : storagePanelTone === "warn"
        ? "Storage health has warnings that should be reviewed soon."
        : "Database, backups, and archives look healthy."
  const storageDetail = dataHealthPending
    ? "Waiting for data-health audit…"
    : [
        dataHealth?.file_sizes_human?.main ? `DB ${dataHealth.file_sizes_human.main}` : null,
        dataHealth?.file_sizes_human?.wal ? `WAL ${dataHealth.file_sizes_human.wal}` : null,
        dataHealth?.latest_backup?.name
          ? `backup ${dataHealth.latest_backup.name}`
          : "no backup found",
      ]
        .filter(Boolean)
        .join(" · ")

  const jobsSummary = jobsPending
    ? "Checking recent grade jobs…"
    : latestGradeJob
      ? `Latest grade job is ${latestGradeJob.status}.`
      : "No recent grade job is recorded yet."
  const jobsDetail = jobsPending
    ? "Waiting for jobs…"
    : latestGradeJob
      ? [
          latestGradeJob.progress_pct > 0 && latestGradeJob.progress_pct < 100
            ? `${latestGradeJob.progress_pct}% complete`
            : null,
          latestGradeJob.message ?? null,
          latestGradeJob.error ?? null,
        ]
          .filter(Boolean)
          .join(" · ")
      : "The jobs panel will light up when grading or cleanup work runs."

  const overallSummary =
    opsPending || dataHealthPending || jobsPending
      ? "Loading system health…"
      : workerTone === "good" &&
          gradingTone === "good" &&
          storagePanelTone === "good" &&
          jobsPanelTone === "good"
        ? "All four core systems are healthy: worker, grading, storage, and jobs are green."
        : [
            workerTone !== "good" ? "worker attention needed" : null,
            gradingTone !== "good" ? "grading gap detected" : null,
            storagePanelTone !== "good" ? "storage warnings present" : null,
            jobsPanelTone !== "good" ? "jobs need review" : null,
          ]
            .filter(Boolean)
            .join(" · ")

  return (
    <div className="monitor-research-page monitor-scroll-region product-page--satellite" data-testid="system-page">
      <main aria-label="System health and diagnostics" className="px-5 pt-5">
        <TerminalPageHeader
          eyebrow="Health"
          title="System"
          description="Snapshot freshness, pipeline diagnostics, and data health for the operator board."
          action={
            <Link to="/" className="btn btn-ghost btn-sm">
              Back to Dashboard
            </Link>
          }
        />
        <p className="mb-4 rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-3 text-sm text-[var(--text-primary)]" data-testid="system-overall-status">
          {overallSummary}
        </p>

        <div className="grid gap-4 md:grid-cols-2" data-testid="system-status-grid">
          <SystemStatusPanel
            title="Worker"
            tone={workerTone}
            summary={workerSummary}
            detail={workerDetail}
            testId="system-worker-panel"
            action={
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => restartWorker.mutate()}
                disabled={restartWorker.isPending}
              >
                {restartWorker.isPending ? "Requesting…" : "Restart worker"}
              </Button>
            }
          />
          <SystemStatusPanel
            title="Grading"
            tone={gradingTone}
            summary={gradingSummary}
            detail={gradingDetail}
            testId="system-grading-panel"
            action={
              gradingGap > 0 ? (
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => gradeLeftover.mutate()}
                  disabled={gradeLeftover.isPending}
                >
                  {gradeLeftover.isPending ? "Starting…" : "Grade leftover"}
                </Button>
              ) : null
            }
          />
          <SystemStatusPanel
            title="Storage"
            tone={storagePanelTone}
            summary={storageSummary}
            detail={storageDetail}
            testId="system-storage-panel"
          />
          <SystemStatusPanel
            title="Jobs"
            tone={jobsPanelTone}
            summary={jobsSummary}
            detail={jobsDetail}
            testId="system-jobs-panel"
          />
        </div>

        <CollapsibleSection
          title="Technical details"
          description="Snapshot diagnostics and storage audit for deeper investigation."
          className="mt-5"
          testId="system-technical-details"
        >
          <div className="space-y-4">
            {predictionTab === "past" ? (
              <div className="term-notice" role="note">
                Past replay diagnostics are tied to the selected replay event on the Dashboard.{" "}
                <Link to="/?tab=past" className="link-subtle">
                  Open Dashboard in Past mode
                </Link>
                .
              </div>
            ) : null}
            {predictionTab === "live" && !isLiveActive ? (
              <div className="term-notice" role="note">
                No live tournament is active. Switch to Upcoming on the Dashboard for pre-event diagnostics.
              </div>
            ) : null}
            <DiagnosticsGradingPanel
              metrics={diagnosticsModel.metrics}
              counters={diagnosticsModel.counters}
              reasonCodes={diagnosticsModel.reasonCodes}
              warnings={diagnosticsModel.warnings}
              selectedEventSummary={diagnosticsModel.selectedEventSummary}
            />
            <DataHealthPanel />
          </div>
        </CollapsibleSection>
      </main>
    </div>
  )
}
