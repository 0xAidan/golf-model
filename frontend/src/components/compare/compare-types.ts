import type {
  FieldBoardPlayer,
  LiveRankingRow,
  LiveTournamentSnapshot,
  MatchupBet,
  TrackRecordPick,
} from "@/lib/types"

export type CompareScope = "event" | "history"

export type CompareEventMode = "current" | "past"

export type CompareEventOption = {
  eventId: string
  label: string
  mode: CompareEventMode
  hasSnapshots?: boolean
  hasGrading?: boolean
}

export type CompareTrackSections = {
  champion: LiveTournamentSnapshot | undefined
  challenger: LiveTournamentSnapshot | null | undefined
  usingLive: boolean
  eventMode?: CompareEventMode
}

export type CompareFieldPlayer = FieldBoardPlayer & {
  champion_composite?: number | null
  challenger_composite?: number | null
  champion_form?: number | null
  challenger_form?: number | null
  champion_course_fit?: number | null
  challenger_course_fit?: number | null
  champion_momentum?: number | null
  challenger_momentum?: number | null
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
  sourceBet: MatchupBet
  championEv: number | null
  challengerEv: number | null
  evDelta: number | null
  championProb: number | null
  challengerProb: number | null
  bucket: MatchupBucket
}

export type CompareKpiSummary = {
  eventName: string
  eventMode: CompareEventMode
  modeLabel: string
  usingLive: boolean
  fieldSize: number
  bothRankedCount: number
  meanAbsRankDelta: number | null
  medianAbsRankDelta: number | null
  overlapBoth: number
  overlapChampionOnly: number
  overlapChallengerOnly: number
  maxDisagreement: { player: string; delta: number } | null
  championGradedPnl?: number | null
  challengerGradedPnl?: number | null
  gradedProfitDelta?: number | null
}

export type GradedPickDiffRow = {
  key: string
  pick: string
  opponent: string
  betType: string
  book: string
  sourcePick: TrackRecordPick
  championEv: number | null
  challengerEv: number | null
  championProfit: number | null
  challengerProfit: number | null
  championHit: boolean | null
  challengerHit: boolean | null
  bucket: MatchupBucket
}

export type SeasonEventCompareRow = {
  eventId: string
  name: string
  eventDate?: string | null
  championPnl: number | null
  challengerPnl: number | null
  profitDelta: number | null
  championHitRate: number | null
  challengerHitRate: number | null
  overlapMatchups: number | null
  picksOnlyChampion: number | null
  picksOnlyChallenger: number | null
  status?: string
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
