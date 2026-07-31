type StatusBannerState = "ready" | "refreshing" | "stale" | "warning" | "error"

const statusLabel: Record<StatusBannerState, string> = {
  ready: "Current",
  refreshing: "Refreshing",
  stale: "Stale data",
  warning: "Attention",
  error: "Data unavailable",
}

type Tone = {
  wrap: string
  dot: string
  label: string
}

const statusTone: Record<StatusBannerState, Tone> = {
  ready: {
    wrap: "border-[rgba(52,211,153,0.28)] bg-[rgba(52,211,153,0.07)]",
    dot: "bg-[var(--op-accent)] shadow-[0_0_10px_-1px_var(--op-accent)]",
    label: "text-[var(--op-accent)]",
  },
  refreshing: {
    wrap: "border-[rgba(96,165,250,0.28)] bg-[rgba(96,165,250,0.07)]",
    dot: "bg-[var(--op-info)] shadow-[0_0_10px_-1px_var(--op-info)] animate-pulse",
    label: "text-[var(--op-info)]",
  },
  stale: {
    wrap: "border-[rgba(251,191,36,0.3)] bg-[rgba(251,191,36,0.07)]",
    dot: "bg-[var(--op-warning)] shadow-[0_0_10px_-1px_var(--op-warning)]",
    label: "text-[var(--op-warning)]",
  },
  warning: {
    wrap: "border-[rgba(251,191,36,0.3)] bg-[rgba(251,191,36,0.07)]",
    dot: "bg-[var(--op-warning)] shadow-[0_0_10px_-1px_var(--op-warning)]",
    label: "text-[var(--op-warning)]",
  },
  error: {
    wrap: "border-[rgba(248,113,113,0.32)] bg-[rgba(248,113,113,0.07)]",
    dot: "bg-[var(--op-negative)] shadow-[0_0_10px_-1px_var(--op-negative)]",
    label: "text-[var(--op-negative)]",
  },
}

export function StatusBanner({ state, message }: { state: StatusBannerState; message: string }) {
  const tone = statusTone[state]
  return (
    <div
      className={`flex items-center gap-3 rounded-[var(--op-radius-sm)] border px-3.5 py-2.5 text-sm ${tone.wrap}`}
      role="status"
      aria-live="polite"
    >
      <span className={`op-dot ${tone.dot}`} aria-hidden="true" />
      <span className={`font-semibold ${tone.label}`}>{statusLabel[state]}</span>
      <span className="text-[var(--op-text-secondary)]">{message}</span>
    </div>
  )
}
