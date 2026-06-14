import { useQuery } from "@tanstack/react-query"

import { api } from "@/lib/api"
import type { DataHealthReport } from "@/lib/types"
import { cn } from "@/lib/utils"

export const DataHealthPanel = () => {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["data-health", 2026],
    queryFn: () => api.getDataHealth(2026),
    staleTime: 60_000,
  })

  const report = (data ?? {}) as DataHealthReport
  const status = report.status ?? "unknown"
  const backup = report.latest_backup
  const archive = report.archive_stats?.latest
  const tableMode = report.table_byte_stats_mode

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
            Database size, retention policy, backups, archives, and 2026 coverage (read-only audit).
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
        {backup?.name ? (
          <p className="data-health-muted" data-testid="data-health-backup">
            Latest backup: <strong>{backup.name}</strong>
            {backup.size_mb != null ? ` (${backup.size_mb} MB)` : null}
            {backup.integrity?.ok === true ? " · integrity ok" : null}
            {backup.integrity?.ok === false ? " · integrity check failed" : null}
          </p>
        ) : (
          <p className="data-health-warn" data-testid="data-health-backup-missing">
            No database backup found in backups/.
          </p>
        )}
        {report.retention_policy?.snapshot_retain_days != null ? (
          <p className="data-health-muted">
            Tick retention: {report.retention_policy.snapshot_retain_days} days
            {report.retention_policy.prune_require_archive ? " · archive required before prune" : null}
            {report.retention_policy.slim_market_payload_enabled ? " · slim market payload on" : null}
          </p>
        ) : null}
        {archive ? (
          <p className="data-health-muted" data-testid="data-health-archive">
            Latest cold archive: {archive.before_utc ?? "unknown window"}
            {archive.valid ? " (verified)" : " (checksum mismatch)"}
          </p>
        ) : null}
        {(report.storage_warnings ?? []).map((w) => (
          <p key={w} className="data-health-warn" role="status">
            {w}
          </p>
        ))}
        {(report.table_byte_stats ?? []).slice(0, 5).length > 0 ? (
          <div>
            <div className="data-health-section-title">
              Largest tables{tableMode === "approximate" ? " (approximate)" : ""}
            </div>
            <ul className="data-health-list">
              {(report.table_byte_stats ?? []).slice(0, 5).map((row) => (
                <li key={row.table}>
                  {row.table}: {row.mb} MB ({row.pct_of_top}%)
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        {report.retention_classifications ? (
          <div>
            <div className="data-health-section-title">Retention matrix</div>
            <ul className="data-health-list">
              <li>KEEP_FOREVER: {(report.retention_classifications.KEEP_FOREVER ?? []).length} tables</li>
              <li>ARCHIVE_THEN_PRUNE: {(report.retention_classifications.ARCHIVE_THEN_PRUNE ?? []).join(", ")}</li>
              <li>SLIM: {(report.retention_classifications.SLIM ?? []).join(", ")}</li>
              <li>INVESTIGATE: {(report.retention_classifications.INVESTIGATE ?? []).join(", ")}</li>
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
