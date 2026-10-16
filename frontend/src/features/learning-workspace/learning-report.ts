import { getReadOnlyJson, type OperatorBoard } from "@/features/operator-data/operator-api"
import type { EvaluationMetrics, LearningReport, LearningReportUnavailable } from "./types"

const record = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v)
const finite = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v)
const strings = (v: unknown): v is string[] => Array.isArray(v) && v.every(x => typeof x === "string")
const count = (v: unknown): v is number => finite(v) && v >= 0
const split = (v: unknown) => record(v) && count(v.events) && count(v.player_events) && [v.start, v.end].every(d => d === null || typeof d === "string")
const metrics = (v: unknown): v is EvaluationMetrics => record(v)
  && ["events", "player_events", "pairs"].every(k => count(v[k]))
  && ["pair_log_loss", "brier", "pair_accuracy", "rank_correlation", "sg_rmse"].every(k => v[k] === null || finite(v[k]))
const event = (v: unknown) => v == null || (record(v)
  && (v.event_id == null || typeof v.event_id === "string" || finite(v.event_id))
  && ["tour", "calendar_start", "snapshot_generated_at", "state", "identity_basis"].every(k => v[k] == null || typeof v[k] === "string")
  && (v.year == null || (finite(v.year) && Number.isInteger(v.year))))

/** V2 calendar identity is resolved by the producer and bound to one exact captured board. */
export function currentProjectionMatchesSnapshot(report: LearningReport | undefined, board: OperatorBoard | undefined): boolean {
  if (report?.schema_version !== 2) return report?.schema_version === 1
  const current = report.current_event
  const boardEvent = board?.event as { tour?: unknown; year?: unknown } | undefined
  const tour = boardEvent?.tour ?? board?.eligibility?.observed_tour
  if (!current || current.state !== "resolved" || !current.tour || current.tour !== tour || !Number.isInteger(current.year)) return false
  if (typeof current.calendar_start !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(current.calendar_start)) return false
  const calendar = new Date(`${current.calendar_start}T00:00:00Z`)
  if (!Number.isFinite(calendar.getTime()) || calendar.toISOString().slice(0,10) !== current.calendar_start || calendar.getUTCFullYear() !== current.year) return false
  const capture = current.snapshot_generated_at
  if (typeof capture !== "string" || !/^\d{4}-\d{2}-\d{2}T/.test(capture) || !Number.isFinite(Date.parse(capture)) || capture !== board?.source?.generated_at) return false
  if (boardEvent?.year != null && String(boardEvent.year) !== String(current.year)) return false
  return true
}

/** Static reports are external data; a successful HTTP response is not a schema guarantee. */
export function readLearningReport(value: unknown): LearningReport | LearningReportUnavailable {
  if (!record(value) || (value.schema_version !== 1 && value.schema_version !== 2)) throw new Error("The learning report format is unavailable.")
  if (value.state === "insufficient_data") {
    const data = record(value.data) ? value.data : {}
    const promotion = record(value.promotion) ? value.promotion : {}
    return {
      schema_version: value.schema_version as 1 | 2, state: "insufficient_data",
      generated_at: typeof value.generated_at === "string" ? value.generated_at : undefined,
      data: { rounds: count(data.rounds) ? data.rounds : undefined, player_events: count(data.player_events) ? data.player_events : undefined, events: count(data.events) ? data.events : undefined },
      reasons: strings(promotion.reasons) ? promotion.reasons : [],
    }
  }
  const r = value
  const valid = ["research", "evaluated"].includes(String(r.state)) && typeof r.generated_at === "string"
    && record(r.candidate) && typeof r.candidate.label === "string" && typeof r.candidate.hash === "string"
    && (r.candidate.trained_through === undefined || typeof r.candidate.trained_through === "string")
    && (r.forward_candidate === undefined || (record(r.forward_candidate) && ["hash", "trained_through", "role", "evaluated_hash"].every(k => typeof (r.forward_candidate as Record<string, unknown>)[k] === "string")))
    && (r.current_rankings_model_hash === undefined || typeof r.current_rankings_model_hash === "string")
    && record(r.baseline) && typeof r.baseline.hash === "string" && typeof r.baseline.source_commit === "string"
    && record(r.data) && ["rounds", "player_events", "events"].every(k => count(r.data && (r.data as Record<string, unknown>)[k]))
    && record(r.selection) && Array.isArray(r.selection.trials) && (r.selection.selected_ridge === null || finite(r.selection.selected_ridge)) && typeof r.selection.objective === "string"
    && record(r.splits) && ["train", "validation", "test"].every(k => split((r.splits as Record<string, unknown>)[k]))
    && record(r.comparisons) && record(r.comparisons.test) && ["candidate", "baseline", "naive"].every(k => metrics((r.comparisons as { test: Record<string, unknown> }).test[k]))
    && ((r.comparisons as { test: Record<string, unknown> }).test.baseline_calibrated === undefined || metrics((r.comparisons as { test: Record<string, unknown> }).test.baseline_calibrated))
    && record(r.promotion) && typeof r.promotion.eligible === "boolean" && strings(r.promotion.reasons)
    && record(r.market_evidence) && count(r.market_evidence.quote_count) && count(r.market_evidence.clv_count) && typeof r.market_evidence.reason === "string"
    && ["roi_pct", "avg_clv_pct"].every(k => (r.market_evidence as Record<string, unknown>)[k] === null || finite((r.market_evidence as Record<string, unknown>)[k]))
    && strings(r.limitations) && Array.isArray(r.current_rankings) && r.current_rankings.every(row => record(row) && typeof row.player_key === "string" && finite(row.rank) && row.rank > 0 && finite(row.expected_sg_per_round))
    && event(r.current_event)
  if (!valid) throw new Error("The learning report is incomplete. A valid report is required before showing a comparison.")
  return r as unknown as LearningReport
}

export const loadLearning = async (signal?: AbortSignal) => readLearningReport(await getReadOnlyJson<unknown>("/reports/learning-latest.json", signal))
