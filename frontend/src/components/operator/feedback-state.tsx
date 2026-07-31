type FeedbackStateKind = "loading" | "empty" | "error" | "unavailable"

const iconFor: Record<FeedbackStateKind, string> = {
  loading: "…",
  empty: "—",
  error: "!",
  unavailable: "—",
}

export function FeedbackState({
  state,
  title,
  detail,
  actionLabel,
  onAction,
}: {
  state: FeedbackStateKind
  title: string
  detail?: string
  actionLabel?: string
  onAction?: () => void
}) {
  const isError = state === "error" || state === "unavailable"
  return (
    <section className="op-card flex flex-col items-center px-6 py-12 text-center" aria-live="polite">
      <span
        aria-hidden="true"
        className={`flex h-11 w-11 items-center justify-center rounded-full border text-lg font-semibold ${
          isError
            ? "border-[rgba(248,113,113,0.35)] bg-[rgba(248,113,113,0.08)] text-[var(--op-negative)]"
            : "border-[var(--op-border-strong)] bg-[var(--op-surface-3)] text-[var(--op-text-secondary)]"
        }`}
      >
        {iconFor[state]}
      </span>
      <h2 className="mt-4 text-base font-semibold text-white">{title}</h2>
      {detail ? <p className="mt-2 max-w-md text-sm text-[var(--op-text-secondary)]">{detail}</p> : null}
      {actionLabel && onAction ? (
        <button type="button" className="op-btn op-btn-ghost mt-5" onClick={onAction}>
          {actionLabel}
        </button>
      ) : null}
    </section>
  )
}
