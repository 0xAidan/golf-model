export type WorkspaceId =
  | "prediction"
  | "players"
  | "matchups"
  | "course"
  | "grading"
  | "track-record"

export type DashboardState = {
  ai_status: {
    available: boolean
    provider?: string
    model?: string
  }
  baseline_provenance?: {
    strategy_source?: string
    live_strategy_name?: string
  }
  latest_outputs?: {
    prediction_markdown_path?: string | null
    backtest_markdown_path?: string | null
    research_markdown_path?: string | null
  }
  latest_prediction_artifact?: OutputArtifact | null
  latest_backtest_artifact?: OutputArtifact | null
  latest_research_artifact?: OutputArtifact | null
  latest_completed_event?: EventSummary | null
  latest_graded_tournament?: GradedTournamentSummary | null
  optimizer?: {
    running?: boolean
    run_count?: number
    last_error?: string | null
  }
  autoresearch?: {
    running?: boolean
    run_count?: number
    last_started_at?: string | null
    last_finished_at?: string | null
    last_error?: string | null
  }
  datagolf?: {
    status?: string
    cached_requests?: number
  }
}

export type LiveRankingRow = {
  rank: number
  player_key?: string
  player: string
  composite: number
  course_fit: number
  form: number
  momentum: number
  momentum_direction?: string
  momentum_trend?: number
  course_confidence?: number
  course_rounds?: number
  weather_adjustment?: number
  finish_state?: string | null
  details?: {
    course_components?: Record<string, number>
    form_components?: Record<string, number>
    momentum_windows?: Record<string, number>
  }
}

export type LiveMatchupRow = {
  player: string
  player_key?: string
  opponent: string
  opponent_key?: string
  bookmaker?: string
  market_odds?: string
  model_prob?: number
  ev?: number
  market_type?: string
  tier?: string
  conviction?: number
  composite_gap?: number
  form_gap?: number
  course_fit_gap?: number
  pick_momentum?: number
  opp_momentum?: number
  momentum_aligned?: boolean
}

export type LiveTournamentSnapshot = {
  event_name?: string
  source_event_id?: string
  source_event_name?: string
  generated_from?: string
  ranking_source?: string
  data_mode?: string
  course_name?: string
  field_size?: number
  tournament_id?: number
  course_num?: number
  active?: boolean
  rankings?: LiveRankingRow[]
  matchups?: LiveMatchupRow[]
  card_path?: string | null
  source_card_path?: string | null
  diagnostics?: {
    market_counts?: Record<string, { raw_rows?: number; reason_code?: string }>
    selection_counts?: {
      input_rows?: number
      selected_rows?: number
    }
    adaptation_state?: string
    reason_codes?: Record<string, number>
    state?: "no_market_posted_yet" | "market_available_no_edges" | "pipeline_error" | "edges_available" | string
    errors?: string[]
  }
}

export type LiveRefreshSnapshot = {
  generated_at?: string
  cadence_mode?: string
  live_tournament?: LiveTournamentSnapshot
  upcoming_tournament?: LiveTournamentSnapshot
  diagnostics?: {
    market_counts?: Record<string, { raw_rows?: number; reason_code?: string }>
    live_state?: string
    upcoming_state?: string
  }
}

export type LiveRefreshStatusResponse = {
  status?: {
    running?: boolean
    cadence_mode?: string
    run_count?: number
    snapshot_age_seconds?: number | null
    last_error?: string | null
  }
  settings?: {
    enabled?: boolean
    autostart?: boolean
    tour?: string
  }
}

export type LiveRefreshSnapshotResponse = {
  ok: boolean
  snapshot: LiveRefreshSnapshot | null
  age_seconds?: number | null
  stale_reason?: string | null
  fallback_reason?: string | null
}

export type OutputArtifact = {
  type?: string
  path: string
  label?: string
  summary?: Record<string, unknown>
}

export type EventSummary = {
  event_id: string
  event_name: string
  year: number
}

export type ScheduleEvent = {
  event_id: string
  event_name: string
  course: string
  start_date?: string | null
  end_date?: string | null
}

export type GradedTournamentSummary = {
  id?: number
  name: string
  course?: string | null
  year?: number | null
  event_id?: string | null
  results_count?: number
  picks_count?: number
  graded_pick_count?: number
  hits?: number
  total_profit?: number
  last_graded_at?: string | null
}

export type GradingHistoryResponse = {
  tournaments: GradedTournamentSummary[]
}

export type TrackRecordPick = {
  player_display: string
  opponent_display: string
  market_odds: string
  bet_type?: string
  hit: number
  profit: number
}

export type TrackRecordEvent = {
  id: number
  name: string
  course?: string
  year?: number
  event_id?: string
  graded_pick_count: number
  hits: number
  wins: number
  pushes: number
  losses: number
  total_profit: number
  last_graded_at?: string
  picks: TrackRecordPick[]
}

export type TrackRecordResponse = {
  events: TrackRecordEvent[]
}

export type PredictionRunRequest = {
  tour: string
  tournament?: string
  course?: string
  mode: "full" | "matchups-only" | "placements-only" | "round-matchups"
  enable_ai: boolean
}

export type CompositePlayer = {
  player_key: string
  player_display: string
  rank: number
  composite: number
  course_fit: number
  form: number
  momentum: number
  momentum_direction?: string
  momentum_trend?: number
  course_confidence?: number
  course_rounds?: number
  weather_adjustment?: number
  details?: {
    course_components?: Record<string, number>
    form_components?: Record<string, number>
    momentum_windows?: Record<string, number>
  }
}

export type MatchupBet = {
  pick: string
  pick_key: string
  opponent: string
  opponent_key: string
  odds: string
  book?: string
  model_win_prob: number
  implied_prob: number
  ev: number
  ev_pct: string
  composite_gap: number
  form_gap: number
  course_fit_gap: number
  reason: string
  adaptation_state?: string
  stake_multiplier?: number
  tier?: string
  pick_momentum?: number
  opp_momentum?: number
  momentum_aligned?: boolean
  conviction?: number
  market_type?: string
}

export type SecondaryBet = {
  player: string
  player_display?: string
  player_key?: string
  bet_type: string
  odds: string
  book?: string
  ev: number
  ev_pct?: string
  is_value?: boolean
  confidence?: string
  reasoning?: string
  recommended_stake?: string
  model_prob?: number
  market_prob?: number
  best_odds?: number
  best_book?: string
}

export type FieldValidation = {
  major_event: boolean
  cross_tour_backfill_used: boolean
  players_checked: number
  players_with_thin_rounds: string[]
  players_missing_dg_skill: string[]
  has_cross_tour_field_risk: boolean
}

export type PredictionRunResponse = {
  status: string
  event_name?: string
  course_name?: string
  course_num?: number
  tournament_id?: number
  field_size?: number
  card_content?: string | null
  card_content_path?: string | null
  output_file?: string | null
  composite_results?: CompositePlayer[]
  matchup_bets?: MatchupBet[]
  value_bets?: Record<string, SecondaryBet[]>
  field_validation?: FieldValidation
  strategy_meta?: {
    strategy_source?: string
    strategy_name?: string
  }
  run_quality?: {
    pass?: boolean
    score?: number
    issues?: string[]
  }
  warnings?: string[]
  errors?: string[]
}

export type PlayerRound = {
  event_name?: string
  event_completed?: string
  score?: number
  sg_total?: number
  fin_text?: string
  round_num?: number
  course_name?: string
}

export type PlayerProfile = {
  player_key: string
  player_display: string
  current_metrics: Record<string, Record<string, number | string | null>>
  recent_rounds: PlayerRound[]
  course_history: PlayerRound[]
  linked_bets: Array<{
    bet_type?: string
    player_display?: string
    opponent_display?: string
    market_odds?: string
    ev?: number
    confidence?: string
    reasoning?: string
  }>
}

export type ResearchProposal = {
  id: number
  title?: string
  hypothesis?: string
  status?: string
  created_at?: string
  expected_edge?: number
}
