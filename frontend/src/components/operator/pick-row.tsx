export type PickRowData = {
  id: string
  player: string
  opponent: string
  market: string
  edge: string
  odds: string
  edgeValue?: number
  winProb?: string
}

export function PickRow({
  pick,
  index,
  maxEdge,
  onSelect,
}: {
  pick: PickRowData
  index?: number
  maxEdge?: number
  onSelect?: (pick: PickRowData) => void
}) {
  const edgeValue = pick.edgeValue ?? 0
  const scale = maxEdge && maxEdge > 0 ? Math.max(8, Math.round((edgeValue / maxEdge) * 100)) : 0

  return (
    <button
      type="button"
      onClick={() => onSelect?.(pick)}
      className="op-focus group grid w-full grid-cols-[auto_1fr_auto] items-center gap-4 border-b border-[var(--op-border)] px-4 py-3.5 text-left transition-colors last:border-b-0 hover:bg-[var(--op-surface-2)] sm:grid-cols-[auto_minmax(0,1fr)_150px_92px_auto]"
      aria-label={`View ${pick.player} versus ${pick.opponent}, edge ${pick.edge}`}
    >
      {typeof index === "number" ? (
        <span className="op-num flex h-7 w-7 items-center justify-center rounded-lg border border-[var(--op-border)] bg-[var(--op-surface-3)] text-xs text-[var(--op-text-secondary)]">
          {index + 1}
        </span>
      ) : (
        <span aria-hidden="true" />
      )}

      <span className="min-w-0">
        <span className="block truncate text-[15px] font-semibold text-white">{pick.player}</span>
        <span className="block truncate text-[13px] text-[var(--op-text-secondary)]">
          over {pick.opponent}
        </span>
      </span>

      <span className="hidden flex-col gap-1.5 sm:flex">
        <span className="op-num text-right text-sm font-semibold text-[var(--op-accent)]">{pick.edge}</span>
        <span className="op-bar" aria-hidden="true">
          <span className="op-bar-fill" style={{ width: `${scale}%` }} />
        </span>
      </span>

      <span className="hidden text-right sm:block">
        <span className="op-num block text-sm text-white">{pick.odds}</span>
        {pick.winProb ? <span className="block text-[11px] text-[var(--op-text-tertiary)]">{pick.winProb} win</span> : null}
      </span>

      <span className="flex items-center justify-end gap-3">
        <span className="op-chip hidden md:inline-flex">{pick.market}</span>
        <span className="op-num text-sm font-semibold text-[var(--op-accent)] sm:hidden">{pick.edge}</span>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true" className="h-4 w-4 text-[var(--op-text-tertiary)] transition-colors group-hover:text-white">
          <path d="m9 6 6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </span>
    </button>
  )
}
