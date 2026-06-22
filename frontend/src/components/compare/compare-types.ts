import type { FieldBoardPlayer, LiveRankingRow, LiveTournamentSnapshot, MatchupBet } from "@/lib/types"

export type CompareScope = "event" | "history"

export type CompareTrackSections = {
  champion: LiveTournamentSnapshot | undefined
  challenger: LiveTournamentSnapshot | null | undefined
  usingLive: boolean
}

export type RankDeltaRow = {
  playerKey: string
  player: string
  championRank: number | null
  challengerRank: number | null
  delta: number | null
}

export type RankScatterPoint = {
  playerKey: string
  player: string
  championRank: number
  challengerRank: number
  delta: number
}

export type ComponentDeltaRow = {
  playerKey: string
  player: string
  rankDelta: number | null
  compositeDelta: number | null
  formDelta: number | null
  courseFitDelta: number | null
  momentumDelta: number | null
}

export type ComponentDriverSummary = {
  composite: number
  form: number
  courseFit: number
  momentum: number
  sampleSize: number
}

export type MatchupBucket = "both" | "champion_only" | "challenger_only"

export type MatchupDiffRow = {
  key: string
  pick: string
  pickKey: string
  opponent: string
  opponentKey: string
  book: string
  championEv: number | null
  challengerEv: number | null
  evDelta: number | null
  championProb: number | null
  challengerProb: number | null
  bucket: MatchupBucket
}

export type CompareKpiSummary = {
  eventName: string
  usingLive: boolean
  fieldSize: number
  bothRankedCount: number
  meanAbsRankDelta: number | null
  medianAbsRankDelta: number | null
  overlapBoth: number
  overlapChampionOnly: number
  overlapChallengerOnly: number
  maxDisagreement: { player: string; delta: number } | null
}

export type MatchupOverlap = {
  both: MatchupBet[]
  championOnly: MatchupBet[]
  challengerOnly: MatchupBet[]
}

export type FieldBoardHighlight = {
  playerKey: string
  player: FieldBoardPlayer
}
