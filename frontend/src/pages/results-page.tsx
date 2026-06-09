import { useEffect, useState } from "react"
import { Link, useSearchParams } from "react-router-dom"

import { GradingPage, TrackRecordPage } from "@/pages/legacy-routes"
import { cn } from "@/lib/utils"

type ResultsTab = "grading" | "track-record"

export function ResultsPage({ initialTab = "grading" }: { initialTab?: ResultsTab }) {
  const [searchParams] = useSearchParams()
  const urlTab = searchParams.get("tab") === "track-record" ? "track-record" : initialTab
  const [tab, setTab] = useState<ResultsTab>(urlTab)

  useEffect(() => {
    setTab(urlTab)
  }, [urlTab])

  return (
    <div className="monitor-research-page monitor-scroll-region" data-testid="results-page">
      <header className="px-5 pt-5 pb-3 border-b border-[var(--border)] bg-[var(--surface)]">
        <p className="text-xs font-semibold uppercase tracking-wider text-[var(--text-tertiary)]">
          Records
        </p>
        <h1 className="mt-1 font-display text-2xl font-bold tracking-tight">Results</h1>
        <p className="mt-1 max-w-2xl text-sm text-[var(--text-secondary)]">
          Grade tournament picks and review track record by model lane (Dashboard vs Lab).
        </p>
        <div className="mt-4 flex flex-wrap gap-2" role="tablist" aria-label="Results views">
          {(
            [
              { id: "grading" as const, label: "Grading" },
              { id: "track-record" as const, label: "Track record" },
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
        <p className="mt-3 text-xs text-[var(--text-tertiary)]">
          Legacy routes still work:{" "}
          <Link to="/grading" className="link-subtle">
            /grading
          </Link>
          ,{" "}
          <Link to="/track-record" className="link-subtle">
            /track-record
          </Link>
        </p>
      </header>
      <div role="tabpanel" className="min-h-0 flex-1">
        {tab === "grading" ? <GradingPage /> : <TrackRecordPage />}
      </div>
    </div>
  )
}
