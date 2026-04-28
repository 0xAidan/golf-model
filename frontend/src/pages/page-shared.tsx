/* eslint-disable react-refresh/only-export-components */
import type { ReactNode } from "react"
import type { LucideIcon } from "lucide-react"

import { Button } from "@/components/ui/button"
import { formatNumber } from "@/lib/format"
import type { MatchupBet } from "@/lib/types"
import { normalizeSportsbook } from "@/lib/prediction-board"

const TIER_STYLE: Record<string, string> = {
  STRONG: "bg-emerald-400/12 text-emerald-300",
  GOOD: "bg-green-500/12 text-green-400",
  LEAN: "bg-slate-400/10 text-slate-400",
}

export const TREND_ARROW: Record<string, string> = { hot: "↑↑", warming: "↑", cooling: "↓", cold: "↓↓" }
export const TREND_COLOR: Record<string, string> = {
  hot: "text-emerald-400",
  warming: "text-emerald-300",
  cooling: "text-amber-300",
  cold: "text-red-400",
}

export const getTierStyle = (tier?: string) => TIER_STYLE[tier ?? ""] ?? TIER_STYLE.LEAN

export function EmptyState({ message }: { message: string }) {
  return <div className="rounded-2xl border border-dashed border-white/10 bg-black/15 px-4 py-8 text-center text-sm text-slate-400">{message}</div>
}

export function InfoRow({
  icon: Icon,
  label,
  value,
}: {
  icon: LucideIcon
  label: string
  value: string
}) {
  return (
    <div className="flex items-center gap-3 rounded-2xl border border-white/8 bg-black/20 px-4 py-3">
      <div className="rounded-xl bg-white/6 p-2 text-green-400">
        <Icon className="h-4 w-4" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-xs uppercase tracking-[0.16em] text-slate-500">{label}</p>
        <p className="truncate text-sm text-slate-100">{value}</p>
      </div>
    </div>
  )
}

export function SelectablePlayerName({
  playerKey,
  label,
  onSelect,
}: {
  playerKey?: string | null
  label: string
  onSelect: (playerKey: string) => void
}) {
  if (!playerKey) {
    return <span className="font-medium text-white">{label}</span>
  }

  return (
    <Button
      type="button"
      variant="link"
      className="h-auto p-0 font-medium text-white underline decoration-transparent underline-offset-4 transition hover:text-green-400 hover:decoration-green-400"
      onClick={() => onSelect(playerKey)}
    >
      {label}
    </Button>
  )
}

export function ChartColumnIcon() {
  return <div className="h-4 w-4 rounded-full bg-green-400/80" aria-hidden="true" />
}

export function buildMatchupKey(matchup: MatchupBet) {
  return [
    matchup.pick_key,
    matchup.opponent_key,
    matchup.market_type ?? "matchup",
    normalizeSportsbook(matchup.book) || "book",
    String(matchup.odds ?? "--"),
  ].join("-")
}

/**
 * Map a backend market key (e.g. "top5", "outright", "make_cut") to a
 * human-readable label for the UI. Falls through to the raw key when unknown.
 */
export function secondaryBadgeLabel(market: string) {
  const normalized = market.toLowerCase().trim()
  // Exact-match well-known market keys produced by the value pipeline.
  const exact: Record<string, string> = {
    outright: "Outright",
    win: "Outright",
    winner: "Outright",
    frl: "First-round leader",
    top5: "Top 5",
    top_5: "Top 5",
    top10: "Top 10",
    top_10: "Top 10",
    top20: "Top 20",
    top_20: "Top 20",
    top30: "Top 30",
    top_30: "Top 30",
    top40: "Top 40",
    top_40: "Top 40",
    make_cut: "Make cut",
    makecut: "Make cut",
    miss_cut: "Miss cut",
    misscut: "Miss cut",
  }
  if (exact[normalized]) return exact[normalized]
  // Pattern fallbacks for variants like "top_5_finish" or "placement_top10".
  const topMatch = normalized.match(/top[_\s-]?(\d+)/)
  if (topMatch) return `Top ${topMatch[1]}`
  if (normalized.includes("miss") && normalized.includes("cut")) return "Miss cut"
  if (normalized.includes("make") && normalized.includes("cut")) return "Make cut"
  if (normalized.includes("first") && normalized.includes("round")) return "First-round leader"
  if (normalized.includes("outright") || normalized === "win" || normalized === "winner") return "Outright"
  // Last-resort: title-case the raw key so we never lose information silently.
  return market.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
}

export function renderTrendValue(direction?: string): ReactNode {
  const arrow = TREND_ARROW[direction ?? ""] ?? "—"
  const trendColor = TREND_COLOR[direction ?? ""] ?? "text-slate-500"

  return <span className={trendColor}>{arrow}</span>
}

export function formatCompositeMetric(value: number | null | undefined) {
  return formatNumber(Number(value ?? 0), 1)
}
