import type { PredictionTab } from "@/hooks/use-prediction-tab"
import type {
  CompositePlayer,
  FlattenedSecondaryBet,
  LiveRefreshSnapshot,
  MatchupBet,
  PlayerProfile,
  StandalonePlayerProfile,
} from "@/lib/types"

export type PlayerProfileLoadState = "loading" | "ready" | "error" | "unavailable"

export type PlayersWorkspaceProps = {
  players: CompositePlayer[]
  liveSnapshot: LiveRefreshSnapshot | null
  snapshotNotice: string | null
  snapshotAgeSeconds: number | null
  predictionTab: PredictionTab
  tournamentId?: number | null
  courseNum?: number | null
  selectedPlayerKey: string
  onPlayerSelect: (playerKey: string) => void
  filteredMatchups: MatchupBet[]
  secondaryBets: FlattenedSecondaryBet[]
  minEdge: number
  richProfilesEnabled: boolean
}

export type LinkedPicksBundle = {
  matchups: MatchupBet[]
  secondary: FlattenedSecondaryBet[]
  totalCount: number
}

export type FieldPercentileMap = {
  composite?: number | null
  form?: number | null
  course_fit?: number | null
  momentum_trend?: number | null
  rank?: number | null
}

export type PlayerWorkspaceData = {
  standalone: StandalonePlayerProfile | undefined
  standaloneState: PlayerProfileLoadState
  standaloneError?: string
  tournament: PlayerProfile | undefined
  tournamentState: PlayerProfileLoadState
  tournamentError?: string
  modelPlayer: CompositePlayer | undefined
  linkedPicks: LinkedPicksBundle
  fieldPercentiles: FieldPercentileMap
  refetchStandalone: () => void
  refetchTournament: () => void
}

export type FieldExplorerSort = "rank" | "composite" | "form" | "trajectory" | "name"
export type FieldExplorerFilter = "field" | "all"
