import type { LiveTournamentSnapshot } from "@/lib/types"

export const DiagnosticsFunnel = ({
  diagnostics,
  emptyMessage,
}: {
  diagnostics?: LiveTournamentSnapshot["diagnostics"]
  emptyMessage?: string
}) => {
  if (!diagnostics && !emptyMessage) return null

  const sel = diagnostics?.selection_counts
  const reasons = diagnostics?.reason_codes ?? {}
  const topReasons = Object.entries(reasons)
    .filter(([, n]) => Number(n) > 0)
    .sort((a, b) => Number(b[1]) - Number(a[1]))
    .slice(0, 6)

  return (
    <div className="diagnostics-funnel" data-testid="diagnostics-funnel">
      {emptyMessage ? (
        <p className="mb-3 text-sm text-[var(--text-secondary)]">{emptyMessage}</p>
      ) : null}
      <div className="diagnostics-funnel__row">
        <span className="diagnostics-funnel__label">Pipeline state</span>
        <span className="metric">{diagnostics?.state ?? "—"}</span>
      </div>
      {sel ? (
        <div className="diagnostics-funnel__row">
          <span className="diagnostics-funnel__label">Candidate funnel</span>
          <span>
            Raw <strong className="metric">{sel.input_rows ?? "—"}</strong>
            {" · "}
            Qualifying <strong className="metric">{sel.all_qualifying_rows ?? "—"}</strong>
            {" · "}
            Selected <strong className="metric">{sel.selected_rows ?? "—"}</strong>
          </span>
        </div>
      ) : null}
      {topReasons.length > 0 ? (
        <div className="diagnostics-funnel__row">
          <span className="diagnostics-funnel__label">Top exclusions</span>
          <span>
            {topReasons.map(([code, count], index) => (
              <span key={code}>
                {index > 0 ? " · " : null}
                {code.replaceAll("_", " ")} ({count})
              </span>
            ))}
          </span>
        </div>
      ) : null}
    </div>
  )
}
