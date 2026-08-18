export function MetricHelp({ label, detail }: { label: string; detail: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-[var(--op-text-secondary)]">
      <span>{label}</span>
      <button
        type="button"
        className="op-focus inline-flex h-[18px] w-[18px] items-center justify-center rounded-full border border-[var(--op-border-strong)] text-[10px] font-semibold text-[var(--op-text-tertiary)] transition-colors hover:border-[var(--op-accent)] hover:text-[var(--op-accent)]"
        aria-label={`About ${label}`}
        title={detail}
      >
        ?
      </button>
    </span>
  )
}
