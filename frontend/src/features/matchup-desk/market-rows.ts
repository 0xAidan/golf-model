import type { OperatorBoard } from "@/features/operator-data/operator-api"

export type MarketFamily = "72h" | "18h" | "group" | "other"
export const MARKET_LABELS: Record<MarketFamily, string> = {
  "72h": "72 holes", "18h": "18 holes", group: "Groups", other: "Other markets",
}
export type DeskRow = {
  id: string; eventId: string; eventName: string; mode: string; market: MarketFamily;
  marketType: string; round: string; player: string; playerKey: string; opponent: string;
  book: string; odds: string; probability: number | null; impliedProbability?: number | null; ev: number | null;
  reason: string; lineAt: string | null; snapshotAt: string | null; eligible: boolean;
}
const str = (v: unknown): string => typeof v === "string" || typeof v === "number" ? String(v) : ""
const num = (v: unknown): number | null => (typeof v === "number" || (typeof v === "string" && v.trim() !== "")) && Number.isFinite(Number(v)) ? Number(v) : null
function roundIdentity(raw: Record<string, unknown>, type: string): string {
  const supplied = str(raw.round_num ?? raw.round_number ?? raw.round).trim()
  if (supplied) return supplied.match(/^(?:r(?:ound)?[_\s-]?)?([1-4])$/i)?.[1] || supplied
  return type.match(/(?:^|[_\s-])(?:round[_\s-]?|r)([1-4])(?:[_\s-]|$)/i)?.[1] || ""
}
export function marketFamily(value: unknown): MarketFamily {
  const v = str(value).toLowerCase().replace(/[\s-]+/g, "_")
  if (/three_?ball|3_?ball|group|two_?ball|2_?ball/.test(v)) return "group"
  if (/round|18_?h|18_?hole/.test(v)) return "18h"
  if (/tournament.*(matchup|h2h)|72_?h|72_?hole/.test(v)) return "72h"
  return "other"
}
export function boardRows(board: OperatorBoard | undefined): DeskRow[] {
  if (!board || ["unavailable", "error"].includes(board.state)) return []
  const items = [...board.picks.matchups, ...board.picks.value_bets]
  const result = new Map<string, DeskRow>()
  for (const raw of items) {
    const player = str(raw.pick || raw.player_display || raw.player || raw.player_key)
    if (!player) continue
    const type = str(raw.market_type || raw.bet_type || raw.market) || "Unspecified market"
    const market = marketFamily(type)
    const round = roundIdentity(raw, type)
    const groupId = str(raw.group_id).trim()
    const marketId = str(raw.market_id).trim()
    const completeMarketIdentity = (market !== "18h" || /^[1-4]$/.test(round)) && (market !== "group" || !!(groupId || marketId))
    const eventId = str(board.event.event_id)
    const playerKey = str(raw.pick_key || raw.player_key || player)
    const opponent = str(raw.opponent || raw.opponent_display)
    const book = str(raw.book || raw.best_book)
    const odds = str(raw.odds ?? raw.best_odds)
    const probability = num(raw.model_win_prob ?? raw.model_prob)
    const implied = num(raw.implied_prob ?? raw.market_prob)
    const identity = [eventId, board.mode, type, round, groupId, playerKey, str(raw.opponent_key || opponent), book, odds]
    // Keep existing saved-card identities stable when no upstream market ID exists.
    if (marketId) identity.push(marketId)
    const id = JSON.stringify(identity)
    const research = raw.shadow_only === true || raw.research_only === true || /shadow|research|simulated/i.test(str(raw.market_provenance))
    result.set(id, {
      id, eventId, eventName: board.event.event_name || "Unknown event", mode: board.mode,
      market, marketType: type, round, player, playerKey, opponent,
      book, odds, probability: probability !== null && probability >= 0 && probability <= 1 ? probability : null,
      impliedProbability: implied !== null && implied >= 0 && implied <= 1 ? implied : null,
      ev: num(raw.ev), reason: str(raw.reason || raw.reasoning || raw.availability_reason),
      lineAt: str(raw.line_seen_at || raw.last_seen_tick) || null,
      snapshotAt: board.source.generated_at || null,
      eligible: !!eventId && !!book && completeMarketIdentity && Number.isFinite(Number(odds)) && Math.abs(Number(odds)) >= 100 && probability !== null && probability >= 0 && probability <= 1 && !research && !/in.?play|^live_/i.test(type) && raw.live_bettable !== false && board.mode === "upcoming" && ["fresh", "refreshing"].includes(board.state),
    })
  }
  return [...result.values()]
}
export function formatProbability(value: number | null): string {
  return value === null ? "—" : `${(value * 100).toFixed(1)}%`
}
export function formatEdge(value: number | null): string {
  return value === null ? "—" : `${value > 0 ? "+" : ""}${(value * 100).toFixed(1)}%`
}
export function formatPrice(value: string): string {
  if (!value) return "—"
  const n = Number(value)
  return Number.isFinite(n) && n >= 100 ? `+${n}` : value
}

export const CARD_KEY = "golf-model.matchup-card.v1"
export type SavedPick = DeskRow & { savedAt: string }
export function readSavedCard(): SavedPick[] {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(CARD_KEY) || "[]")
    return Array.isArray(value) ? value.filter((v): v is SavedPick => !!v && typeof v === "object" &&
      ["id", "player", "eventId", "eventName", "mode", "marketType", "round", "playerKey", "opponent", "book", "odds", "reason", "savedAt"].every(key => typeof v[key] === "string") &&
      ["72h", "18h", "group", "other"].includes(v.market) &&
      (v.probability === null || (typeof v.probability === "number" && Number.isFinite(v.probability) && v.probability >= 0 && v.probability <= 1)) &&
      (v.ev === null || (typeof v.ev === "number" && Number.isFinite(v.ev))) &&
      (v.snapshotAt === null || typeof v.snapshotAt === "string") && (v.lineAt === null || typeof v.lineAt === "string")) : []
  } catch { return [] }
}
