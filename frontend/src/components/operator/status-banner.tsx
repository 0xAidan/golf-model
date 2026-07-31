type StatusBannerState = "ready" | "refreshing" | "stale" | "warning" | "error"

const statusLabel: Record<StatusBannerState, string> = {
  ready: "Current",
  refreshing: "Refreshing",
  stale: "Stale data",
  warning: "Attention",
  error: "Data unavailable",
}

const statusClass: Record<StatusBannerState, string> = {
  ready: "border-emerald-400/30 bg-emerald-400/10 text-emerald-100",
  refreshing: "border-emerald-400/30 bg-emerald-400/10 text-emerald-100",
  stale: "border-amber-400/40 bg-amber-400/10 text-amber-100",
  warning: "border-amber-400/40 bg-amber-400/10 text-amber-100",
  error: "border-red-400/40 bg-red-400/10 text-red-100",
}

export function StatusBanner({ state, message }: { state: StatusBannerState; message: string }) {
  return (
    <section className={`border px-3 py-2 text-sm ${statusClass[state]}`} role="status" aria-live="polite">
      <span className="mr-2 font-semibold">{statusLabel[state]}</span>
      <span className="text-current/90">{message}</span>
    </section>
  )
}
