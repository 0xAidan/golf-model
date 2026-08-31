import { useLiveSnapshot } from "@/providers/live-snapshot-provider"

export function DatabaseRebuildBanner() {
  const { dbUnavailable, dbRestoreInProgress } = useLiveSnapshot()

  if (!dbUnavailable) return null

  return (
    <div
      className="status-banner status-banner--danger"
      role="alert"
      data-testid="db-rebuild-banner"
    >
      <p className="status-banner__title">Database file is damaged</p>
      <p className="status-banner__message">
        {dbRestoreInProgress
          ? "A backup restore is running. Last boards stay on this screen."
          : "You are seeing the last saved boards. The site will rebuild after a backup restore."}
      </p>
    </div>
  )
}
