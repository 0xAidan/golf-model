export type Metrics = {
  decisions: number; events: number; wins: number; losses: number; zero_return: number;
  unit_profit: number | null; unit_stake: number | null; unit_roi_pct: number | null;
  max_drawdown_units: number | null; brier: number | null; log_loss: number | null;
  probability_n: number; probability_coverage_pct: number | null; clv_bps: number | null; closing_line_n: number;
}
export type PerformanceEvent = {
  event_key: string; event_name: string; event_start: string; event_end: string;
  decisions: number; unit_profit: number; unit_roi_pct: number | null;
  cumulative_profit: number; drawdown_units: number; brier: number | null; probability_n: number;
}
export type PerformanceScope = {
  summary: Metrics;
  interval: { method: string; unit_roi_pct_95: [number, number] | null; brier_95: [number, number] | null; events: number; replicates: number };
  series: PerformanceEvent[];
  monthly: Array<{ month: string; decisions: number; unit_profit: number; unit_roi_pct: number | null }>;
  reliability: Array<{ lower: number; upper: number; n: number; predicted: number; observed: number }>;
  models: Array<Metrics & { key: string }>;
  books: Array<Metrics & { key: string }>;
}
export type PerformanceReport = {
  schema_version: 1; as_of: string; basis: string; default_cohort: string;
  dimensions: { markets: string[]; lanes: string[]; models: string[]; books: string[] };
  cohorts: Record<string, { label: string; description?: string }>;
  scopes: Record<string, PerformanceScope>;
  provenance: Record<string, unknown>; caveats: string[];
}
export type EvaluationMetrics = {
  pair_log_loss: number | null; brier: number | null; pair_accuracy: number | null;
  rank_correlation: number | null; sg_rmse: number | null;
  events: number; player_events: number; pairs: number;
}
export type LearningReport = {
  schema_version: 1 | 2; generated_at: string; state: "evaluated" | "research";
  candidate: { id: string; hash: string; label: string; method: string; feature_names: string[]; ranking_unit: string; trained_through?: string };
  baseline: { id: string; label: string; hash: string; source_commit: string; preserved: boolean; comparison_kind: string };
  data: { rounds: number; player_events: number; events: number; first_event: string; last_event: string; source_sha256: string };
  splits: Record<string, { events: number; player_events: number; start: string; end: string; event_ids: string[] }>;
  selection: { objective: string; trials: Array<{ ridge: number; validation_log_loss: number | null }>; selected_ridge: number | null };
  comparisons: {
    test: { candidate: EvaluationMetrics; baseline: EvaluationMetrics; baseline_calibrated?: EvaluationMetrics; naive: EvaluationMetrics };
    delta: Record<string, number | null>;
    event_series: Array<{ event_id: string; year: number; date: string; event_name: string; players: number; pairs: number; candidate_log_loss: number; baseline_log_loss: number; candidate_brier: number; baseline_brier: number; candidate_rank_correlation: number; baseline_rank_correlation: number }>;
  };
  market_evidence: { state: string; quote_count: number; clv_count: number; roi_pct: number | null; avg_clv_pct: number | null; reason: string };
  promotion: { eligible: boolean; decision: string; reasons: string[] };
  forward_candidate?: { hash: string; trained_through: string; role: string; evaluated_hash: string };
  current_rankings_model_hash?: string;
  protocol?: { test_status?: string };
  current_event?: {
    event_id?: string | number | null; event_name?: string; as_of?: string;
    tour?: string | null; year?: number | null; calendar_start?: string | null;
    snapshot_generated_at?: string | null; state?: string; identity_basis?: string;
  } | null;
  current_rankings: Array<{ player_key: string; player_display: string; rank: number; expected_sg_per_round: number; history_rounds: number; last_observed: string; feature_coverage: number }>;
  limitations: string[];
}

export type LearningReportUnavailable = {
  schema_version: 1 | 2; state: "insufficient_data"; generated_at?: string;
  data: { rounds?: number; player_events?: number; events?: number }; reasons: string[];
}
export type HistoryCoverageReport = {
  schema_version: 1; state: "recovered_source_inventory"; as_of: string;
  summary: { complete_card_versions: number; named_event_labels: number; indexed_observations: number; payloads_with_observations: number };
  events: Array<{ label: string; card_versions: number; first_generated: string | null; last_generated: string | null; observations: number; status: string }>;
  gaps: string[]; basis: string;
}
