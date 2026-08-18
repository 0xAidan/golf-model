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
      className="@container/pick op-focus group flex w-full items-center gap-3 border-b border-[var(--op-border)] px-4 py-3.5 text-left transition-colors last:border-b-0 hover:bg-[var(--op-surface-2)]"
      aria-label={`View ${pick.player} versus ${pick.opponent}, edge ${pick.edge}`}
    >
      {typeof index === "number" ? (
        <span className="op-num flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-[var(--op-border)] bg-[var(--op-surface-3)] text-xs text-[var(--op-text-secondary)]">
          {index + 1}
        </span>
      ) : (
        <span aria-hidden="true" className="w-0" />
      )}

      <span className="min-w-[10rem] flex-1">
        <span className="block text-[15px] font-semibold leading-snug text-white">{pick.player}</span>
        <span className="block text-[13px] leading-snug text-[var(--op-text-secondary)]">
          over {pick.opponent}
        </span>
      </span>

      <span className="hidden w-[7.5rem] shrink-0 flex-col gap-1.5 @min-[480px]/pick:flex">
        <span className="op-num text-right text-sm font-semibold text-[var(--op-accent)]">{pick.edge}</span>
        <span className="op-bar" aria-hidden="true">
          <span className="op-bar-fill" style={{ width: `${scale}%` }} />
        </span>
      </span>

      <span className="hidden w-[4.5rem] shrink-0 text-right @min-[560px]/pick:block">
        <span className="op-num block text-sm text-white">{pick.odds}</span>
        {pick.winProb ? <span className="block text-[11px] text-[var(--op-text-tertiary)]">{pick.winProb} win</span> : null}
      </span>

      <span className="flex shrink-0 items-center justify-end gap-3">
        <span className="hidden @min-[600px]/pick:inline-flex">
          <span className="op-chip">{pick.market}</span>
        </span>
        <span className="op-num text-sm font-semibold text-[var(--op-accent)] @min-[480px]/pick:hidden">{pick.edge}</span>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true" className="h-4 w-4 text-[var(--op-text-tertiary)] transition-colors group-hover:text-white">
          <path d="m9 6 6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </span>
    </button>
  )
}
