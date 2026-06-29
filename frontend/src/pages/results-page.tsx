import { useEffect, useState } from "react"
import { useSearchParams } from "react-router-dom"

import { AnalyticsWorkspacePage } from "@/pages/analytics-workspace-page"
import { GradingPage } from "@/pages/legacy-routes"
import { TerminalPageHeader } from "@/components/ui/terminal-page-header"
import { cn } from "@/lib/utils"

type ResultsTab = "grading" | "analytics"

export function ResultsPage({ initialTab = "grading" }: { initialTab?: ResultsTab }) {
  const [searchParams] = useSearchParams()
  const urlTab = searchParams.get("tab") === "analytics" ? "analytics" : initialTab
  const [tab, setTab] = useState<ResultsTab>(urlTab)

  useEffect(() => {
    setTab(urlTab)
  }, [urlTab])

  return (
    <div className="monitor-research-page monitor-scroll-region product-page--satellite" data-testid="results-page">
      <TerminalPageHeader
        eyebrow="Records"
        title="Results"
        description="Grade tournament picks and explore season analytics with filters and presets."
      />
      <div className="px-5 pb-3">
        <div className="flex flex-wrap gap-2" role="tablist" aria-label="Results views">
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
                "rounded-md border px-3 py-1.5 text-sm font-medium transition-colors",
                tab === item.id
                  ? "border-[var(--green)] bg-[var(--green-bg)] text-[var(--green)]"
                  : "border-[var(--border)] bg-[var(--surface)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]",
              )}
              onClick={() => setTab(item.id)}
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
