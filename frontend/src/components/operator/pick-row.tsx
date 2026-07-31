export type PickRowData = {
  id: string
  player: string
  opponent: string
  market: string
  edge: string
  odds: string
}

export function PickRow({ pick, onSelect }: { pick: PickRowData; onSelect?: (pick: PickRowData) => void }) {
  return (
    <button
      type="button"
      onClick={() => onSelect?.(pick)}
      className="grid min-h-11 w-full grid-cols-[1fr_auto] gap-3 border-b border-slate-800 px-3 py-2 text-left hover:bg-slate-800/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-emerald-300 sm:grid-cols-[minmax(0,1fr)_110px_80px_80px]"
      aria-label={`View ${pick.player} versus ${pick.opponent}`}
    >
      <span><span className="font-medium text-white">{pick.player}</span><span className="text-slate-400"> over {pick.opponent}</span></span>
      <span className="hidden text-slate-400 sm:block">{pick.market}</span>
      <span className="operator-num text-emerald-300">{pick.edge}</span>
      <span className="operator-num text-right text-slate-300">{pick.odds}</span>
    </button>
  )
}
