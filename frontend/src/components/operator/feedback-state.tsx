type FeedbackStateKind = "loading" | "empty" | "error" | "unavailable"

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
  const icon = state === "error" ? "!" : state === "loading" ? "…" : "—"
  return (
    <section className="border border-slate-700 bg-slate-900/70 px-4 py-8 text-center" aria-live="polite">
      <p aria-hidden="true" className="text-xl text-slate-400">{icon}</p>
      <h2 className="mt-2 text-base font-semibold text-white">{title}</h2>
      {detail ? <p className="mx-auto mt-2 max-w-md text-sm text-slate-400">{detail}</p> : null}
      {actionLabel && onAction ? (
        <button
          type="button"
          className="mt-4 min-h-11 border border-slate-600 px-3 text-sm font-medium text-white hover:border-emerald-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-300"
          onClick={onAction}
        >
          {actionLabel}
        </button>
      ) : null}
    </section>
  )
}
