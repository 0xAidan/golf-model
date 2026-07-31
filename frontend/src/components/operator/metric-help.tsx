export function MetricHelp({ label, detail }: { label: string; detail: string }) {
  return (
    <span className="inline-flex items-center gap-1">
      <span>{label}</span>
      <button
        type="button"
        className="inline-flex min-h-6 min-w-6 items-center justify-center rounded-full border border-slate-600 text-xs text-slate-300 hover:border-slate-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-300"
        aria-label={`About ${label}`}
        title={detail}
      >
        ?
      </button>
    </span>
  )
}
