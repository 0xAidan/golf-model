import type { MatchupBet } from "@/lib/types"
import { formatNumber, formatPercent } from "@/lib/format"
import { normalizeSportsbook } from "@/lib/prediction-board"
import { getTierStyle } from "@/pages/page-shared"
import { cn } from "@/lib/utils"

export type PickRowProps = {
  bet: MatchupBet
  marketLabel?: string
  gradedResult?: "win" | "loss" | "push" | "void"
  className?: string
  onExpand?: () => void
  expanded?: boolean
}

const formatMarketLabel = (bet: MatchupBet, override?: string) => {
  if (override) return override
  const mt = bet.market_type ?? ""
  if (mt.includes("round")) return `Round ${mt.replace(/\D/g, "") || "matchup"}`
  if (mt.includes("top")) return mt.replace(/_/g, " ")
  return "72-hole"
}

const gradedBadgeClass = (result: PickRowProps["gradedResult"]) => {
  switch (result) {
    case "win":
      return "pick-row__grade pick-row__grade--win"
    case "loss":
      return "pick-row__grade pick-row__grade--loss"
    case "push":
      return "pick-row__grade pick-row__grade--push"
    case "void":
      return "pick-row__grade pick-row__grade--void"
    default:
      return null
  }
}

export function PickRow({
  bet,
  marketLabel,
  gradedResult,
  className,
  onExpand,
  expanded = false,
}: PickRowProps) {
  const book = normalizeSportsbook(bet.book) || bet.book || "—"
  const tier = bet.tier ?? "LEAN"
  const gradeClass = gradedBadgeClass(gradedResult ?? bet.graded_result)

  return (
    <article
      className={cn("pick-row", className)}
      data-testid="pick-row"
      data-tier={tier}
    >
      <div className="pick-row__main">
        <span className="pick-row__market">{formatMarketLabel(bet, marketLabel)}</span>
        <div className="pick-row__players">
          <span className="pick-row__pick">{bet.pick}</span>
          {bet.opponent ? (
            <>
              <span className="pick-row__vs">vs</span>
              <span className="pick-row__opponent">{bet.opponent}</span>
            </>
          ) : null}
        </div>
        <span className="pick-row__edge num">{formatPercent(bet.ev)}</span>
        <span className="pick-row__odds num">
          {bet.odds} · {book}
        </span>
        <span className="pick-row__probs">
          <span className="num">{formatPercent(bet.model_win_prob)}</span>
          <span className="pick-row__prob-sep">/</span>
          <span className="num pick-row__implied">{formatPercent(bet.implied_prob)}</span>
        </span>
        <span className={cn("pick-row__tier", getTierStyle(tier))}>{tier}</span>
        {gradeClass ? <span className={gradeClass}>{gradedResult ?? bet.graded_result}</span> : null}
      </div>
      {onExpand ? (
        <button
          type="button"
          className="pick-row__expand btn btn-ghost btn-xs"
          onClick={onExpand}
          aria-expanded={expanded}
        >
          {expanded ? "Hide detail" : "Detail"}
        </button>
      ) : null}
      {bet.reason && expanded ? (
        <p className="pick-row__reason">{bet.reason}</p>
      ) : null}
      {bet.composite_gap != null && expanded ? (
        <p className="pick-row__meta num">Composite gap {formatNumber(bet.composite_gap, 2)}</p>
      ) : null}
    </article>
  )
}
