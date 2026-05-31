import { useQuery } from "@tanstack/react-query"

import { api } from "@/lib/api"

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

const statusColor = (status: string | undefined) => {
  if (status === "green") return "var(--green, #22c55e)"
  if (status === "red") return "var(--red, #ef4444)"
  return "var(--amber, #f59e0b)"
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
      className="card"
      style={{ marginBottom: 12 }}
      data-testid="data-health-panel"
    >
      <div className="card-header">
        <div>
          <h2
            id="data-health-heading"
            className="card-title"
            style={{ margin: 0, fontSize: 13 }}
          >
            Data health
          </h2>
          <div className="card-desc">
            Database size, 2026 history coverage, and storage warnings (read-only audit).
          </div>
        </div>
        <span
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: 10,
            fontWeight: 700,
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            color: statusColor(status),
          }}
          data-testid="data-health-status"
        >
          {status}
        </span>
      </div>
      <div className="card-body" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {isLoading ? (
          <p style={{ margin: 0, fontSize: 11, color: "var(--text-muted)" }}>Loading audit…</p>
        ) : null}
        {isError ? (
          <p style={{ margin: 0, fontSize: 11, color: "var(--red, #ef4444)" }} role="alert">
            {(error as Error)?.message ?? "Failed to load data health"}
          </p>
        ) : null}
        {!isLoading && !isError && report.summary ? (
          <p style={{ margin: 0, fontSize: 12, color: "var(--text)", lineHeight: 1.45 }}>
            {report.summary}
          </p>
        ) : null}
        {report.file_sizes_human?.main ? (
          <p style={{ margin: 0, fontSize: 11, color: "var(--text-muted)" }}>
            Main DB: <strong>{report.file_sizes_human.main}</strong>
            {report.file_sizes_human.wal ? ` · WAL: ${report.file_sizes_human.wal}` : null}
          </p>
        ) : null}
        {(report.storage_warnings ?? []).map((w) => (
          <p
            key={w}
            style={{ margin: 0, fontSize: 11, color: "var(--amber, #f59e0b)" }}
            role="status"
          >
            {w}
          </p>
        ))}
        {(report.table_byte_stats ?? []).slice(0, 5).length > 0 ? (
          <div>
            <div
              style={{
                fontSize: 10,
                fontFamily: "var(--font-mono)",
                color: "var(--text-muted)",
                marginBottom: 4,
              }}
            >
              Largest tables
            </div>
            <ul style={{ margin: 0, paddingLeft: 16, fontSize: 11 }}>
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
            <div
              style={{
                fontSize: 10,
                fontFamily: "var(--font-mono)",
                color: "var(--text-muted)",
                marginBottom: 4,
              }}
            >
              2026 monthly picks
            </div>
            <ul style={{ margin: 0, paddingLeft: 16, fontSize: 11 }}>
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
            <div style={{ fontSize: 10, color: "var(--text-muted)", marginBottom: 4 }}>Gaps</div>
            <ul style={{ margin: 0, paddingLeft: 16, fontSize: 11 }}>
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
