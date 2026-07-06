import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Star } from "lucide-react"
import { toast } from "sonner"
import { useSearchParams } from "react-router-dom"

import { AnalyticsWorkspacePage } from "@/pages/analytics-workspace-page"
import { GradingPage } from "@/pages/legacy-routes"
import { Button } from "@/components/ui/button"
import { PageHeader } from "@/components/ui/page-header"
import { api } from "@/lib/api"
import { cn } from "@/lib/utils"

type ResultsTab = "grading" | "analytics"

export function ResultsPage({ initialTab = "grading" }: { initialTab?: ResultsTab }) {
  const [searchParams, setSearchParams] = useSearchParams()
  const queryClient = useQueryClient()
  const urlTab = searchParams.get("tab") === "analytics" ? "analytics" : initialTab
  const [tab, setTab] = useState<ResultsTab>(urlTab)
  const [gradeJobId, setGradeJobId] = useState<string | null>(null)
  const [gradeJobProgress, setGradeJobProgress] = useState<number | null>(null)

  const dashboardQuery = useQuery({
    queryKey: ["dashboard-state"],
    queryFn: api.getDashboardState,
    staleTime: 60_000,
  })

  useEffect(() => {
    setTab(urlTab)
  }, [urlTab])

  const gradeMutation = useMutation({
    mutationFn: () =>
      api.startGradeJob({
        event_id: dashboardQuery.data?.latest_completed_event?.event_id,
        year: dashboardQuery.data?.latest_completed_event?.year,
        event_name: dashboardQuery.data?.latest_completed_event?.event_name,
      }),
    onSuccess: (job) => {
      setGradeJobId(job.job_id)
      setGradeJobProgress(0)
      toast.message("Grading started — you can keep using the page.")
    },
    onError: (error) => {
      const message =
        error instanceof Error && error.message
          ? error.message
          : "Grading failed to start. Check System health."
      toast.error(message)
    },
  })

  useEffect(() => {
    if (!gradeJobId) return
    let cancelled = false

    const poll = async () => {
      try {
        const job = await api.getOpsJob(gradeJobId)
        if (cancelled) return
        setGradeJobProgress(job.progress_pct)
        if (job.status === "running" || job.status === "pending") return

        setGradeJobId(null)
        setGradeJobProgress(null)

        const result = job.result as
          | {
              status?: string
              reason?: string
              error?: string
              message?: string
            }
          | undefined
        const status = String(result?.status ?? job.status ?? "").toLowerCase()

        if (job.status === "error" || result?.error) {
          toast.error(job.error ?? result?.error ?? "Grading failed.")
          return
        }

        if (status === "captured" && result?.reason === "awaiting_results") {
          toast.message("Results not ready yet — auto-grade will retry when Data Golf publishes final results.")
        } else {
          toast.success(job.message ?? "Event graded successfully")
        }

        void queryClient.invalidateQueries({ queryKey: ["dashboard-state"] })
        void queryClient.invalidateQueries({ queryKey: ["grading-history"] })
        void queryClient.invalidateQueries({ queryKey: ["grading-season"] })
        void queryClient.invalidateQueries({ queryKey: ["track-record"] })
        void queryClient.invalidateQueries({ queryKey: ["live-refresh-past-events"] })
        void queryClient.invalidateQueries({ queryKey: ["live-refresh-past-snapshot"] })
        void queryClient.invalidateQueries({ queryKey: ["live-refresh-past-market-rows"] })
      } catch {
        if (!cancelled) {
          setGradeJobId(null)
          setGradeJobProgress(null)
        }
      }
    }

    void poll()
    const intervalId = window.setInterval(() => void poll(), 2000)
    return () => {
      cancelled = true
      window.clearInterval(intervalId)
    }
  }, [gradeJobId, queryClient])

  const handleTabChange = (nextTab: ResultsTab) => {
    setTab(nextTab)
    const nextParams = new URLSearchParams(searchParams)
    if (nextTab === initialTab) {
      nextParams.delete("tab")
    } else {
      nextParams.set("tab", nextTab)
    }
    setSearchParams(nextParams, { replace: true })
  }

  const latestCompletedEvent = dashboardQuery.data?.latest_completed_event
  const gradeDisabled = gradeMutation.isPending || Boolean(gradeJobId) || !latestCompletedEvent
  const gradeLabel = gradeJobId
    ? `Grading… ${gradeJobProgress ?? 0}%`
    : gradeMutation.isPending
      ? "Starting…"
      : "Grade event"

  return (
    <div className="monitor-research-page monitor-scroll-region product-page--satellite" data-testid="results-page">
      <PageHeader
        eyebrow="Records"
        title="Results"
        description="Grade tournament picks and explore season analytics with filters and presets."
        action={
          <Button
            type="button"
            variant="default"
            size="sm"
            onClick={() => gradeMutation.mutate()}
            disabled={gradeDisabled}
            data-testid="results-grade-action"
            title={
              latestCompletedEvent
                ? `Grade ${latestCompletedEvent.event_name}`
                : "No completed event is ready to grade yet."
            }
          >
            <Star size={14} />
            {gradeLabel}
          </Button>
        }
      />
      <div className="px-5 pb-1">
        <div
          className="inline-flex flex-wrap gap-2 rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-1"
          role="tablist"
          aria-label="Results views"
        >
          {(
            [
              { id: "grading" as const, label: "Grading" },
              { id: "analytics" as const, label: "Analytics" },
            ] as const
          ).map((item) => (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={tab === item.id}
              className={cn(
                "rounded-lg border px-3 py-1.5 text-sm font-medium transition-colors",
                tab === item.id
                  ? "border-[var(--green)] bg-[var(--green-bg)] text-[var(--green)]"
                  : "border-[var(--border)] bg-[var(--surface)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]",
              )}
              onClick={() => handleTabChange(item.id)}
              data-testid={`results-tab-${item.id}`}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>
      <div role="tabpanel" className="flex-1">
        {tab === "grading" ? <GradingPage /> : <AnalyticsWorkspacePage />}
      </div>
    </div>
  )
}
