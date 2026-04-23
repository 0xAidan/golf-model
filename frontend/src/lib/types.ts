export type WorkspaceId =
  | "prediction"
  | "players"
  | "matchups"
  | "course"
  | "grading"
  | "track-record"
  | "champion-challenger"

export type ChampionChallengerBrier = {
  model_name: string
  brier: number | null
  n: number
}

export type ChampionChallengerMatchupRoi = {
  model_name: string
  bets: number
  staked: number
  pnl: number
  roi_pct: number | null
}

export type ChampionChallengerClv = {
  model_name: string
  clv_bps: number | null
  n: number
}

export type ChampionChallengerWindow = {
  brier: ChampionChallengerBrier
  matchup_roi: ChampionChallengerMatchupRoi
  clv: ChampionChallengerClv
}

export type ChampionChallengerModelSummary = {
  model_name: string
  windows: Record<string, ChampionChallengerWindow>
}

export type ChampionChallengerSummary = {
  champion: string
  challengers: string[]
  windows_days: number[]
  models: ChampionChallengerModelSummary[]
}

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
  availability?: Record<string, number | string | null>
  form_flags?: string[]
  form_notes?: string[]
  details?: {
    course_components?: Record<string, number>
    form_components?: Record<string, number>
    momentum_windows?: Record<string, number>
    form_flags?: string[]
    form_notes?: string[]
    availability?: Record<string, number | string | null>
  }
}

export type LiveLeaderboardRow = {
  rank: number
  position?: string
  player_key?: string
  player: string
  total_to_par?: number | null
  latest_round_num?: number | null
  latest_round_score?: number | null
  rounds_played?: number
  finish_state?: string | null
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

export type VerificationError = {
  code?: string
  summary?: string
  details?: string
  action?: string
  retryable?: boolean
  observed_event_id?: string
  observed_tour?: string
  field_source?: string
  failed_invariants?: string[]
}

export type EligibilityInfo = {
  verified?: boolean
  field_event_id?: string
  field_player_count?: number
  field_source?: string
  failed_invariants?: string[]
  summary?: string
  details?: string
  action?: string | null
  code?: string
  retryable?: boolean
  major_event?: boolean
  cross_tour_backfill_used?: boolean
  observed_tour?: string
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
  /**
   * Format of the underlying event. `"team"` indicates a Foursomes/Fourball
   * team event (e.g. Zurich Classic) for which the individual-stroke-play
   * pipeline is intentionally skipped; callers should render a notice in
   * place of placement / matchup boards. Absent or `"individual"` means the
   * normal pipeline ran.
   */
  event_format?: "individual" | "team"
  /**
   * When the pipeline short-circuits, the reason code (currently only
   * `"team_event"`). Safe to ignore when `event_format` is individual.
   */
  skipped_reason?: string
  active?: boolean
  completed_replay?: boolean
  leaderboard_source?: string
  in_play_parse_note?: string | null
  live_point_in_time_source?: string | null
  leaderboard?: LiveLeaderboardRow[]
  rankings?: LiveRankingRow[]
  live_rankings?: LiveRankingRow[]
  pre_tournament_rankings?: LiveRankingRow[]
  frozen_pre_teeoff_rankings?: LiveRankingRow[]
  matchups?: LiveMatchupRow[]
  matchup_bets?: MatchupBet[]
  matchup_bets_all_books?: MatchupBet[]
  value_bets?: Record<string, SecondaryBet[]>
  card_path?: string | null
  source_card_path?: string | null
  eligibility?: EligibilityInfo
  verification_error?: VerificationError
  diagnostics?: {
    market_counts?: Record<string, { raw_rows?: number; reason_code?: string }>
    selection_counts?: {
      input_rows?: number
      selected_rows?: number
      all_qualifying_rows?: number
    }
    adaptation_state?: string
    reason_codes?: Record<string, number>
    value_filters?: {
      missing_display_odds?: number
      ev_cap_filtered?: number
      probability_inconsistency_filtered?: number
    }
    books_seen?: string[]
    books_with_qualifying_edges?: string[]
    books_after_card_caps?: string[]
    book_stats?: Record<string, { lines_seen?: number; qualifying_edges?: number; card_rows?: number }>
    state?: "no_market_posted_yet" | "market_available_no_edges" | "pipeline_error" | "edges_available" | "team_event" | "eligibility_failed" | string
    errors?: string[]
  }
}

export type DataSource = "live" | "replay" | "fixture"

export type LiveRefreshSnapshot = {
  generated_at?: string
  data_source?: DataSource | string
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
  generated_at?: string | null
  age_seconds?: number | null
  stale_after_seconds?: number | null
  stale_reason?: string | null
  fallback_reason?: string | null
}

export type PastSnapshotEvent = {
  event_id: string
  event_name: string
  latest_generated_at?: string | null
  snapshot_count?: number
}

export type PastSnapshotEventsResponse = {
  events: PastSnapshotEvent[]
}

export type PastSnapshotResponse = {
  ok: boolean
  event_id?: string
  snapshot_id?: string
  generated_at?: string | null
  tour?: string | null
  section?: string
  snapshot?: LiveTournamentSnapshot | null
  error?: string
}

export type PastTimelinePoint = {
  snapshot_id: string
  generated_at?: string | null
  tour?: string | null
  cadence_mode?: string | null
  section: string
  event_id?: string | null
  event_name?: string | null
  active: boolean
  diagnostics_state?: string | null
  leaderboard_count: number
  rankings_count: number
  matchup_count: number
  value_pick_count: number
  best_edge?: number | null
}

export type PastTimelineResponse = {
  ok: boolean
  event_id: string
  section: string
  point_count: number
  points: PastTimelinePoint[]
  error?: string
}

export type PastMarketPredictionRow = {
  id?: number
  snapshot_id: string
  generated_at?: string | null
  tour?: string | null
  section: string
  event_id: string
  event_name?: string | null
  market_family: string
  market_type?: string | null
  player_key?: string | null
  player_display?: string | null
  opponent_key?: string | null
  opponent_display?: string | null
  book?: string | null
  odds?: string | null
  model_prob?: number | null
  implied_prob?: number | null
  ev?: number | null
  is_value?: number | null
  is_value_bool?: boolean
  payload?: Record<string, unknown>
  payload_json?: string
}

export type PastMarketRowsResponse = {
  ok: boolean
  event_id: string
  market_family?: string | null
  section?: string | null
  row_count: number
  rows: PastMarketPredictionRow[]
  error?: string
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
  availability?: Record<string, number | string | null>
  form_flags?: string[]
  form_notes?: string[]
  details?: {
    course_components?: Record<string, number>
    form_components?: Record<string, number>
    momentum_windows?: Record<string, number>
    form_flags?: string[]
    form_notes?: string[]
    availability?: Record<string, number | string | null>
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

export type FlattenedSecondaryBet = {
  market: string
  player: string
  player_display?: string
  player_key?: string
  odds: string
  ev: number
  confidence?: string
  book?: string
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
  matchup_bets_all_books?: MatchupBet[]
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
  header?: {
    dg_rank?: number | null
    owgr_rank?: number | null
    dg_skill_estimate?: number | null
    field_size?: number
    tee_time?: string | null
    field_status?: string | null
    recent_rounds_tracked?: number
    course_rounds_tracked?: number
    latest_event_name?: string | null
    latest_event_completed?: string | null
  }
  skill_breakdown?: {
    primary?: Array<{ key: string; label: string; value: number }>
    approach_buckets?: Array<{ key: string; label: string; value: number }>
    component_deltas?: Array<{ key: string; label: string; value: number }>
    summary?: {
      best_area?: { key: string; label: string; value: number } | null
      weakest_area?: { key: string; label: string; value: number } | null
      dg_rank?: number | null
      owgr_rank?: number | null
      dg_skill_estimate?: number | null
    }
  }
  rolling_form?: {
    windows?: Record<string, number | null>
    window_source_map?: Record<string, string>
    benchmarks?: Record<string, Record<string, number | null>>
    trend_series?: number[]
    summary?: {
      delta_short_vs_medium?: number | null
      rounds_in_sample?: number
    }
  }
  course_event_context?: {
    recent_starts?: Array<{
      event_name?: string | null
      event_completed?: string | null
      fin_text?: string | null
      rounds_recorded?: number
      avg_sg_total?: number | null
    }>
    recent_summary?: {
      events_tracked?: number
      made_cuts?: number
      avg_sg_total?: number | null
    }
    course_summary?: {
      rounds_tracked?: number
      avg_sg_total?: number | null
      best_round_sg?: number | null
      worst_round_sg?: number | null
    }
  }
  betting_context?: {
    summary?: {
      linked_bet_count?: number
      average_ev?: number | null
      high_confidence_count?: number
    }
    strongest_linked_bet?: {
      bet_type?: string
      player_display?: string
      opponent_display?: string
      market_odds?: string
      ev?: number
      confidence?: string
      reasoning?: string
    } | null
  }
  metric_labels?: Record<string, string>
  sections_version?: number
}

export type ResearchProposal = {
  id: number
  title?: string
  hypothesis?: string
  status?: string
  created_at?: string
  expected_edge?: number
}

export type StandalonePlayerProfile = {
  player_key: string
  player_display: string
  header: {
    player_display: string
    dg_rank?: number | null
    owgr_rank?: number | null
    dg_skill_estimate?: number | null
    primary_tour?: string | null
    rounds_in_db?: number
    events_tracked?: number
  }
  sg_skills: {
    sg_total?: number | null
    sg_ott?: number | null
    sg_app?: number | null
    sg_arg?: number | null
    sg_putt?: number | null
    driving_dist?: number | null
    driving_acc?: number | null
  }
  approach_buckets: Array<{ key: string; label: string; value: number }>
  rolling_windows: { "10"?: number | null; "25"?: number | null; "50"?: number | null }
  trend_series: number[]
  recent_events: Array<{
    event_name: string
    event_completed?: string | null
    fin_text?: string | null
    avg_sg_total?: number | null
    rounds_played?: number
  }>
  ranking_data?: Record<string, unknown> | null
  has_skill_data: boolean
  has_ranking_data: boolean
  has_approach_data: boolean
}
