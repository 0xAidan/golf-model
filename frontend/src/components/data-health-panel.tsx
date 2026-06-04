import { useQuery } from "@tanstack/react-query"

import { api } from "@/lib/api"
import { cn } from "@/lib/utils"

type DataHealthReport = {
  status?: string
  summary?: string
  file_sizes_human?: Record<string, string>
  storage_warnings?: string[]
  gaps?: Array<{ type: string; detail: string }>
  monthly_coverage?: Record<
    string,
    {
      tournaments?: number
      picks?: number
      prediction_log?: number
      market_prediction_rows?: number
    }
  >
  table_byte_stats?: Array<{ table: string; mb: number; pct_of_top: number }>
  row_counts?: Record<string, number>
}

export const DataHealthPanel = () => {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["data-health", 2026],
    queryFn: () => api.getDataHealth(2026),
    staleTime: 60_000,
  })

  const report = (data ?? {}) as DataHealthReport
  const status = report.status ?? "unknown"

  return (
    <section
      aria-labelledby="data-health-heading"
      className="card data-health-card"
      data-testid="data-health-panel"
    >
      <div className="card-header">
        <div>
          <h2 id="data-health-heading" className="card-title data-health-title">
            Data health
          </h2>
          <div className="card-desc">
            Database size, 2026 history coverage, and storage warnings (read-only audit).
          </div>
        </div>
        <span
          className={cn(
            "data-health-status",
            status === "green" && "data-health-status--green",
            status === "red" && "data-health-status--red",
            status !== "green" && status !== "red" && "data-health-status--amber",
          )}
          data-testid="data-health-status"
        >
          {status}
        </span>
      </div>
      <div className="card-body data-health-body">
        {isLoading ? <p className="data-health-muted">Loading audit…</p> : null}
        {isError ? (
          <p className="data-health-error" role="alert">
            {(error as Error)?.message ?? "Failed to load data health"}
          </p>
        ) : null}
        {!isLoading && !isError && report.summary ? (
          <p className="data-health-summary">{report.summary}</p>
        ) : null}
        {report.file_sizes_human?.main ? (
          <p className="data-health-muted">
            Main DB: <strong>{report.file_sizes_human.main}</strong>
            {report.file_sizes_human.wal ? ` · WAL: ${report.file_sizes_human.wal}` : null}
          </p>
        ) : null}
        {(report.storage_warnings ?? []).map((w) => (
          <p key={w} className="data-health-warn" role="status">
            {w}
          </p>
        ))}
        {(report.table_byte_stats ?? []).slice(0, 5).length > 0 ? (
          <div>
            <div className="data-health-section-title">Largest tables</div>
            <ul className="data-health-list">
              {(report.table_byte_stats ?? []).slice(0, 5).map((row) => (
                <li key={row.table}>
                  {row.table}: {row.mb} MB
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        {report.monthly_coverage ? (
          <div>
            <div className="data-health-section-title">2026 monthly picks</div>
            <ul className="data-health-list">
              {Object.entries(report.monthly_coverage)
                .filter(([, c]) => (c.picks ?? 0) > 0 || (c.tournaments ?? 0) > 0)
                .map(([mo, c]) => (
                  <li key={mo}>
                    {mo}: {c.tournaments ?? 0} events, {c.picks ?? 0} picks
                  </li>
                ))}
            </ul>
          </div>
        ) : null}
        {(report.gaps ?? []).length > 0 ? (
          <div>
            <div className="data-health-section-title">Gaps</div>
            <ul className="data-health-list">
              {report.gaps!.map((g) => (
                <li key={g.detail}>{g.detail}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    </section>
  )
}
