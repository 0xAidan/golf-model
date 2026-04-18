import rawTrackRecordData from "@/data/trackRecord.json"
import type { TrackRecordEvent } from "@/lib/types"

type StaticTrackRecordPick = {
  pick: string
  opponent: string
  odds: string
  result: string
  pl: number
}

type StaticTrackRecordEvent = {
  name: string
  course: string
  record: {
    wins: number
    losses: number
    pushes: number
  }
  profit_units: number
  picks: StaticTrackRecordPick[]
}

type StaticTrackRecordData = {
  events: StaticTrackRecordEvent[]
}

export type MergedTrackRecordEvent = {
  name: string
  course: string
  wins: number
  losses: number
  pushes: number
  profit: number
  picks: StaticTrackRecordPick[]
}

export type TrackRecordTotals = {
  wins: number
  losses: number
  pushes: number
  profit: number
}

function isStaticTrackRecordPick(value: unknown): value is StaticTrackRecordPick {
  if (typeof value !== "object" || value === null) return false

  const candidate = value as Record<string, unknown>
  return (
    typeof candidate.pick === "string"
    && typeof candidate.opponent === "string"
    && typeof candidate.odds === "string"
    && typeof candidate.result === "string"
    && typeof candidate.pl === "number"
  )
}

function isStaticTrackRecordEvent(value: unknown): value is StaticTrackRecordEvent {
  if (typeof value !== "object" || value === null) return false

  const candidate = value as Record<string, unknown>
  const record = candidate.record

  if (typeof record !== "object" || record === null) return false

  const recordCandidate = record as Record<string, unknown>

  return (
    typeof candidate.name === "string"
    && typeof candidate.course === "string"
    && typeof candidate.profit_units === "number"
    && typeof recordCandidate.wins === "number"
    && typeof recordCandidate.losses === "number"
    && typeof recordCandidate.pushes === "number"
    && Array.isArray(candidate.picks)
    && candidate.picks.every(isStaticTrackRecordPick)
  )
}

function isStaticTrackRecordData(value: unknown): value is StaticTrackRecordData {
  if (typeof value !== "object" || value === null) return false

  const candidate = value as Record<string, unknown>
  return Array.isArray(candidate.events) && candidate.events.every(isStaticTrackRecordEvent)
}

export function getStaticTrackRecordEvents(): StaticTrackRecordEvent[] {
  return isStaticTrackRecordData(rawTrackRecordData) ? rawTrackRecordData.events : []
}

export function mergeTrackRecordEvents(apiEvents: TrackRecordEvent[], staticEvents = getStaticTrackRecordEvents()) {
  const seen = new Set<string>()
  const merged: MergedTrackRecordEvent[] = []

  for (const apiEvent of apiEvents) {
    const key = apiEvent.name.toLowerCase().trim()
    seen.add(key)

    const apiPicks = (apiEvent.picks ?? []).map((pick) => ({
      pick: pick.player_display,
      opponent: pick.opponent_display,
      odds: String(pick.market_odds ?? "--"),
      result: pick.hit === 1 ? "win" : pick.profit === 0 ? "push" : "loss",
      pl: pick.profit,
    }))

    const staticMatch = staticEvents.find((event) => event.name.toLowerCase().trim() === key)
    merged.push({
      name: apiEvent.name,
      course: apiEvent.course ?? staticMatch?.course ?? "",
      wins: apiEvent.wins,
      losses: apiEvent.losses,
      pushes: apiEvent.pushes,
      profit: apiEvent.total_profit,
      picks: apiPicks.length > 0 ? apiPicks : staticMatch?.picks ?? [],
    })
  }

  for (const staticEvent of staticEvents) {
    const key = staticEvent.name.toLowerCase().trim()
    if (seen.has(key)) continue

    merged.push({
      name: staticEvent.name,
      course: staticEvent.course,
      wins: staticEvent.record.wins,
      losses: staticEvent.record.losses,
      pushes: staticEvent.record.pushes,
      profit: staticEvent.profit_units,
      picks: staticEvent.picks,
    })
  }

  const totals = merged.reduce<TrackRecordTotals>(
    (accumulator, event) => ({
      wins: accumulator.wins + event.wins,
      losses: accumulator.losses + event.losses,
      pushes: accumulator.pushes + event.pushes,
      profit: accumulator.profit + event.profit,
    }),
    { wins: 0, losses: 0, pushes: 0, profit: 0 },
  )

  return { events: merged, totals }
}
