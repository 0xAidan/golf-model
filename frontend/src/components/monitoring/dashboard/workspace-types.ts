import type { PredictionTab } from "@/hooks/use-prediction-tab"
import type {
  CompositePlayer,
  FlattenedSecondaryBet,
  GradedTournamentSummary,
  LiveRefreshSnapshot,
  LiveTournamentSnapshot,
  MatchupBet,
  PastMarketPredictionRow,
  PlayerProfile,
  PredictionRunResponse,
  RecordSummary,
} from "@/lib/types"

export type PastReplaySource = "dashboard" | "lab"
export type PastReplayLane = "completed" | "live" | "upcoming"
export type PastHistoryLane = "live" | "upcoming" | "lab_live" | "lab_upcoming"

export type WorkspaceFullPicksProduction = {
  matchups: MatchupBet[]
  matchupsEmptyMessage: string
  matchupDiagnostics?: LiveTournamentSnapshot["diagnostics"]
  minEdgePct: number
  secondaryBets: FlattenedSecondaryBet[]
  onPlayerSelect?: (playerKey: string) => void
  marketRows?: PastMarketPredictionRow[]
  marketRowsLoading?: boolean
  marketRowsError?: string
}

export type WorkspaceFullPicksLab = WorkspaceFullPicksProduction & {
  tournamentId: number | null | undefined
  profileName?: string
  predictionRun: PredictionRunResponse | null
}

export type WorkspaceFullPicksEmbed =
  | ({ mode: "production" } & WorkspaceFullPicksProduction)
  | ({ mode: "lab" } & WorkspaceFullPicksLab)

export type PredictionWorkspacePageProps = {
  liveSnapshot: LiveRefreshSnapshot | null
  runtimeStatus: { label: string; tone: "good" | "warn" | "bad" }
  snapshotNotice: string | null
  snapshotAgeSeconds: number | null
  predictionTab: PredictionTab
  onPredictionTabChange: (value: PredictionTab) => void
  availableBooks: string[]
  selectedBooks: string[]
  onSelectedBooksChange: (value: string[]) => void
  matchupSearch: string
  onMatchupSearchChange: (value: string) => void
  minEdge: number
  onMinEdgeChange: (value: number) => void
  filteredMatchups: MatchupBet[]
  gradingHistory: GradedTournamentSummary[]
  gradingRecordSummary?: RecordSummary
  players: CompositePlayer[]
  predictionRun: PredictionRunResponse | null
  selectedPlayerKey: string
  onPlayerSelect: (playerKey: string) => void
  selectedPlayerProfile?: PlayerProfile
  playerProfileState: "loading" | "ready" | "error" | "unavailable"
  playerProfileErrorMessage?: string
  onPlayerProfileRetry: () => void
  richProfilesEnabled: boolean
  secondaryBets: FlattenedSecondaryBet[]
  powerRankingsSubtitle?: string | null
  pastReplaySource?: PastReplaySource
  onPastEventContextChange?: (context: { eventName: string; courseName?: string } | null) => void
  /** Dashboard latest completed event — default past replay selection. */
  preferredPastEventId?: string
  usingProdSnapshotFallback?: boolean
  labLanePartialSections?: boolean
  /** Embedded Full picks / Full lab picks tab content from App.tsx */
  fullPicks?: WorkspaceFullPicksEmbed
  /** Market rows for production full picks (optional; App provides when available) */
  marketRows?: PastMarketPredictionRow[]
  marketRowsLoading?: boolean
  marketRowsError?: string
}
