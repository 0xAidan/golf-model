export type WorkspaceId =
  | "prediction"
  | "lab-board"
  | "players"
  | "matchups"
  | "grading"
  | "track-record"
  | "legacy-model"
  | "champion-challenger"
  | "diagnostics"

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
  current_rank?: number | null
  start_rank?: number | null
  rank_delta?: number | null
  start_composite?: number | null
  pre_tournament_composite?: number | null
  ranking_source?: string | null
  live_point_in_time_source?: string | null
  leaderboard_rank?: number | null
  leaderboard_position?: string | null
  start_leaderboard_rank?: number | null
  start_leaderboard_position?: string | null
  leaderboard_delta?: number | null
  leaderboard_baseline_source?: string | null
  total_to_par?: number | null
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
  leaderboard_rank?: number | null
  leaderboard_position?: string | null
  start_leaderboard_rank?: number | null
  start_leaderboard_position?: string | null
  leaderboard_delta?: number | null
  leaderboard_baseline_source?: string | null
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
  model_variant?: string
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
  live_player_board?: LivePlayerBoardRow[]
  eliminated_players?: Array<{
    player_key?: string
    player?: string
    finish_state?: string | null
    pre_tournament_composite?: number | null
  }>
  live_stats_by_player?: Record<string, Record<string, unknown>>
  live_stats_source?: string
  live_stats_fetched_at?: string
  live_stats_age_seconds?: number | null
  live_stats_fresh?: boolean
  live_model_mode?: "full_live_stats" | "leaderboard_only" | "stale_live_stats" | "no_live_stats" | string
  live_stats_warning?: string | null
  live_groups_shadow?: Record<string, unknown>[]
  live_player_markets_shadow?: Record<string, unknown>[]
  live_groups_display_enabled?: boolean
  live_player_markets_display_enabled?: boolean
  live_opportunity_alerts?: LiveOpportunityAlert[]
  scoring_baseline_label?: string
  ranking_fallback_reason?: string | null
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
    failed_candidates?: FailedMatchupCandidate[]
    state?: "no_market_posted_yet" | "market_available_no_edges" | "pipeline_error" | "edges_available" | "team_event" | "eligibility_failed" | string
    errors?: string[]
    /** Append-only shadow Monte Carlo rows written for this snapshot tick (when flags enabled). */
    shadow_mc_rows_written?: number
    market_rows_written?: number
    market_rows_write_error?: string
  }
}

export type LivePlayerBoardRow = {
  player_key?: string
  player?: string
  finish_state?: string | null
  model?: {
    start_rank?: number | null
    current_rank?: number | null
    rank_delta?: number | null
    composite?: number | null
    start_composite?: number | null
    pre_tournament_composite?: number | null
    momentum?: number | null
    momentum_trend?: number | null
    momentum_direction?: string | null
  }
  scoring?: {
    position_label?: string | null
    position_rank?: number | null
    start_position?: string | null
    start_position_rank?: number | null
    position_delta?: number | null
    total_to_par?: number | null
    baseline_source?: string | null
    live_stats?: Record<string, unknown> | null
  }
}

export type LiveOpportunityAlert = {
  opportunity_key: string
  is_new_live_opportunity?: boolean
  is_material_ev_increase?: boolean
  first_seen_at?: string | null
  ev?: number | null
  market_family?: string | null
  market_type?: string | null
  bookmaker?: string | null
  player?: string | null
  opponent?: string | null
}

export type FailedMatchupCandidate = {
  pick: string
  opponent: string
  composite_gap?: number
  model_win_prob?: number
  platt_win_prob?: number
  dg_win_prob?: number | null
  implied_prob?: number
  book?: string | null
  odds?: number | null
  ev?: number | null
  ev_pct?: string | null
  reason_code: "below_ev_threshold" | "dg_model_disagreement" | string
  market_type?: string
}

export type DataSource = "live" | "replay" | "fixture"

export type LiveRefreshSnapshot = {
  generated_at?: string
  data_source?: DataSource | string
  cadence_mode?: string
  live_tournament?: LiveTournamentSnapshot
  upcoming_tournament?: LiveTournamentSnapshot
  legacy_tournament?: LiveTournamentSnapshot
  /** Parallel lab lane (same shape as production sections); null when disabled or failed. */
  lab_live_tournament?: LiveTournamentSnapshot | null
  lab_upcoming_tournament?: LiveTournamentSnapshot | null
  diagnostics?: {
    market_counts?: Record<string, { raw_rows?: number; reason_code?: string }>
    live_state?: string
    upcoming_state?: string
    legacy_state?: string
    lab_live_state?: string | null
    lab_upcoming_state?: string | null
  }
}

export type LiveRefreshProgressPayload = {
  refresh_state?: string
  phase?: string | null
  phase_detail?: string | null
  progress_updated_at?: string | null
  progress_started_at?: string | null
  percent?: number | null
  last_error?: string | null
}

export type LiveRefreshRuntimeStatus = {
  running?: boolean
  cadence_mode?: string
  run_count?: number
  snapshot_age_seconds?: number | null
  last_error?: string | null
  refresh_state?: string
  progress?: LiveRefreshProgressPayload
  worker_pidfile?: string
  worker_running?: boolean
  runtime_owner?: string
}

export type LiveRefreshStatusResponse = {
  status?: LiveRefreshRuntimeStatus
  settings?: {
    enabled?: boolean
    autostart?: boolean
    tour?: string
  }
}

export type LiveRefreshSnapshotResponse = {
  ok: boolean
  /** True when server returns 409 — another recompute holds the lock. */
  busy?: boolean
  snapshot: LiveRefreshSnapshot | null
  generated_at?: string | null
  age_seconds?: number | null
  stale_after_seconds?: number | null
  stale_reason?: string | null
  fallback_reason?: string | null
  data_state?: string | null
  operator_message?: string | null
  split_brain_suspected?: boolean
  accepted?: boolean
  /** Present on 409 busy responses — merged live-refresh status snapshot. */
  status?: LiveRefreshRuntimeStatus
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
  source?: "dashboard" | "lab" | string
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
  source?: "dashboard" | "lab" | string
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
  market_stats?: RecordSummary
  variant_stats?: Record<string, { picks: number; hits: number; profit: number }>
  picks?: TrackRecordPick[]
}

export type RecordBucket = {
  picks: number
  wins: number
  losses: number
  pushes: number
  profit: number
  hit_rate: number | null
}

export type RecordSummary = {
  outrights: RecordBucket
  matchups: RecordBucket
  combined: RecordBucket
}

export type GradingHistoryResponse = {
  tournaments: GradedTournamentSummary[]
  summary?: RecordSummary
}

export type TrackRecordPick = {
  model_variant?: string
  source?: string | null
  market_book?: string | null
  player_display: string
  opponent_display?: string
  market_odds?: string
  bet_type?: string
  model_prob?: number | null
  ev?: number | null
  reasoning?: string | null
  hit: number
  profit: number
  actual_finish?: string | null
  graded_at?: string | null
  outcome?: "win" | "loss" | "push"
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
  market_stats?: RecordSummary
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
  current_rank?: number | null
  start_rank?: number | null
  rank_delta?: number | null
  start_composite?: number | null
  pre_tournament_composite?: number | null
  leaderboard_rank?: number | null
  leaderboard_position?: string | null
  start_leaderboard_rank?: number | null
  start_leaderboard_position?: string | null
  leaderboard_delta?: number | null
  leaderboard_baseline_source?: string | null
  total_to_par?: number | null
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
  /** Backend tier gate explanation (EV vs composite gap). */
  tier_rationale?: string
  tier_drivers?: Record<string, unknown>
  /** ``matchup_ratio`` vs ``matchup_v5_tie_aware`` — do not mix with outright ``value_decimal`` EV. */
  ev_kind?: string
  pick_momentum?: number
  opp_momentum?: number
  momentum_aligned?: boolean
  conviction?: number
  market_type?: string
  /** When set (replay payload or upstream), overrides leaderboard-derived grade in Past tab. */
  graded_result?: "win" | "loss" | "push"
  is_new_live_opportunity?: boolean
  is_new_since_last_snapshot?: boolean
  is_material_ev_increase?: boolean
  first_seen_at?: string
  live_bettable?: boolean
  market_provenance?: string
  availability_reason?: string
  line_seen_at?: string | null
  last_seen_tick?: string | null
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
  is_new_live_opportunity?: boolean
  is_material_ev_increase?: boolean
  first_seen_at?: string
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
  is_new_live_opportunity?: boolean
  is_material_ev_increase?: boolean
  first_seen_at?: string
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
  /** Snapshot model lane (e.g. lab ``baseline`` vs production ``v5``). */
  model_variant?: string
  /** Snapshot ranking provenance when present (e.g. DG in-play vs model-only). */
  ranking_source?: string
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
    lab_champion_id?: string
    lab_champion_primary_roi_pct?: number
    lab_champion_holdout_roi_pct?: number
  }
  run_quality?: {
    pass?: boolean
    score?: number
    issues?: string[]
  }
  warnings?: string[]
  errors?: string[]
  /** Which snapshot section hydrated this run (for upcoming vs live correctness). */
  hydration_section?: HydrationSectionKey
  live_model_mode?: string
  live_stats_fresh?: boolean
}

export type HydrationSectionKey =
  | "upcoming"
  | "live"
  | "legacy"
  | "upcoming_fallback_live"
  | "live_fallback_upcoming"

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

/** One row in ``recent_rounds_sample`` on standalone player profiles (API + round log UI). */
export type StandaloneRecentRoundSample = {
  round_num?: number | null
  event_name?: string | null
  event_completed?: string | null
  event_id?: string | null
  course_name?: string | null
  tour?: string | null
  score?: number | null
  sg_total?: number | null
  sg_ott?: number | null
  sg_app?: number | null
  sg_arg?: number | null
  sg_putt?: number | null
  sg_t2g?: number | null
  driving_dist?: number | null
  driving_acc?: number | null
  gir?: number | null
  scrambling?: number | null
  fin_text?: string | null
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
  rolling_windows_expanded?: Record<
    "sg_total" | "sg_ott" | "sg_app" | "sg_arg" | "sg_putt" | "sg_t2g",
    { "10"?: number | null; "25"?: number | null; "50"?: number | null }
  >
  trend_series: number[]
  recent_events: Array<{
    event_name: string
    event_completed?: string | null
    event_id?: string | null
    course_name?: string | null
    tour?: string | null
    fin_text?: string | null
    avg_score?: number | null
    avg_to_par?: number | null
    avg_sg_total?: number | null
    avg_sg_ott?: number | null
    avg_sg_app?: number | null
    avg_sg_arg?: number | null
    avg_sg_putt?: number | null
    avg_sg_t2g?: number | null
    rounds_played?: number
  }>
  recent_rounds_sample?: StandaloneRecentRoundSample[]
  course_summaries?: Array<{
    course_name: string
    rounds_played: number
    avg_sg_total?: number | null
  }>
  ranking_card?: {
    dg_rank?: number | null
    owgr_rank?: number | null
    dg_skill_estimate?: number | null
    primary_tour?: string | null
    player_name?: string | null
    extra_scalars?: Record<string, number>
  }
  ranking_data?: Record<string, unknown> | null
  has_skill_data: boolean
  has_ranking_data: boolean
  has_approach_data: boolean
}

/** `GET /api/calibration/by-market` */
export type CalibrationByMarketBucket = {
  probability_bucket: string
  predicted_avg: number | null
  actual_hit_rate: number | null
  sample_size: number
  correction_factor: number | null
  updated_at?: string | null
}

export type CalibrationByMarketResponse = {
  bet_types: string[]
  curves: Record<string, CalibrationByMarketBucket[]>
  min_sample_for_correction?: number
}

/** `GET /api/clv/summary` */
export type ClvSummarySegment = {
  market_book: string
  n_bets: number
  avg_clv_pct: number | null
  significant: boolean
}

export type ClvSummaryResponse = {
  overall: { n_bets: number; avg_clv_pct: number | null; significant: boolean }
  by_book: ClvSummarySegment[]
  min_bets_for_significance?: number
}

/** `GET /api/research/ab-report` */
export type ResearchAbReportPairedKey = {
  market_family: string
  market_type: string
  player_key: string
  opponent_key: string
  book: string
}

export type ResearchAbReportPairedSample = {
  key: ResearchAbReportPairedKey
  v5_model_prob: number | null
  legacy_model_prob: number | null
  v5_ev: number | null
  legacy_ev: number | null
}

export type ResearchAbReportResponse = {
  ok: boolean
  error?: string
  event_id?: string
  row_limit?: number
  counts?: {
    raw_rows?: number
    v5_keys?: number
    legacy_keys?: number
    paired_keys?: number
    v5_only_keys?: number
    legacy_only_keys?: number
  }
  paired_metrics?: {
    mean_model_prob_delta_v5_minus_legacy?: number | null
    mean_ev_delta_v5_minus_legacy?: number | null
    n_prob_pairs?: number
    n_ev_pairs?: number
  }
  paired_samples?: ResearchAbReportPairedSample[]
  truncated_paired_samples?: boolean
  artifact_paths?: { json?: string; markdown?: string }
}

export type TrackConfigRow = {
  id?: number
  track: "dashboard" | "lab" | string
  model_variant?: string | null
  config_hash?: string | null
  label?: string | null
  status?: string | null
  activated_by?: string | null
  activation_reason?: string | null
  activated_at?: string | null
  strategy_bundle?: Record<string, unknown> | null
}

export type TracksResponse = {
  tracks: Partial<Record<"dashboard" | "lab", TrackConfigRow>>
  effective_config_hash: Partial<Record<"dashboard" | "lab", string | null>>
  history: TrackConfigRow[]
}

export type FieldBoardPlayer = {
  player_key: string
  player: string
  champion_rank: number | null
  challenger_rank: number | null
  rank_delta: number | null
  composite: number | null
  course_fit: number | null
  form: number | null
  momentum: number | null
  momentum_direction?: string | null
  momentum_trend?: number | null
  course_confidence?: number | null
  finish_state?: string | null
  leaderboard_position?: string | null
  leaderboard_delta?: number | null
  total_to_par?: number | null
  form_flags?: string[]
  matchup_count: number
  in_positive_ev: boolean
  sg?: Record<string, number | null> | null
  has_sg: boolean
}

export type FieldBoardResponse = {
  section: "live" | "upcoming" | string
  event_name?: string | null
  tournament_id?: number | null
  generated_at?: string | null
  snapshot_id?: string | null
  lab_available: boolean
  player_count: number
  players: FieldBoardPlayer[]
}

export type PromotionGate = {
  id: string
  passed: boolean
  detail: string
}

export type PromotionReadinessResponse = {
  promotion_enabled: boolean
  passed: boolean
  gates: PromotionGate[]
  metrics?: Record<string, unknown>
  lab_graded_positive_ev?: number
}

export type TrackMetrics = {
  n: number
  graded_with_odds: number
  wins: number
  hit_rate_pct: number | null
  roi_pct: number | null
  pnl_units: number | null
  brier: number | null
  low_sample: boolean
}

export type TrackComparisonResponse = {
  window: string
  window_days: number
  market?: string | null
  book?: string | null
  tracks: { cockpit: TrackMetrics; lab: TrackMetrics }
  overlap: { both: number; cockpit_only: number; lab_only: number }
  by_market: Record<string, Record<string, TrackMetrics>>
  data_kind: string
  note: string
}

export type DataHealthBackupInfo = {
  path?: string
  name?: string
  size_mb?: number
  created?: string
  integrity?: {
    ok?: boolean
    quick_check?: string
    error?: string
  }
}

export type DataHealthArchiveInfo = {
  exports_dir?: string
  archive_count?: number
  latest?: {
    path?: string
    created_at?: string
    before_utc?: string
    valid?: boolean
    row_counts?: Record<string, number>
  } | null
}

export type DataHealthReport = {
  ok?: boolean
  status?: string
  summary?: string
  file_sizes_human?: Record<string, string>
  storage_warnings?: string[]
  gaps?: Array<{ type: string; detail: string }>
  monthly_coverage?: Record<
    string,
    {
      tournaments?: number
      picks?: number
      prediction_log?: number
      market_prediction_rows?: number
    }
  >
  table_byte_stats?: Array<{
    table: string
    mb: number
    pct_of_top: number
    approximate?: boolean
  }>
  table_byte_stats_mode?: "dbstat" | "approximate"
  row_counts?: Record<string, number>
  retention_policy?: {
    retain_forever?: string[]
    prunable_tick_tables?: string[]
    snapshot_retain_days?: number
    prune_require_archive?: boolean
    slim_market_payload_enabled?: boolean
  }
  retention_classifications?: {
    KEEP_FOREVER?: string[]
    ARCHIVE_THEN_PRUNE?: string[]
    SLIM?: string[]
    INVESTIGATE?: string[]
  }
  latest_backup?: DataHealthBackupInfo | null
  archive_stats?: DataHealthArchiveInfo
}
