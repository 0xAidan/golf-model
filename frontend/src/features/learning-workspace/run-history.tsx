import { useQuery } from "@tanstack/react-query"
import { ArrowDownToLine, RefreshCw } from "lucide-react"
import { getReadOnlyJson } from "@/features/operator-data/operator-api"
import { number, shortDate } from "./charts"

type Run = {
  run_id: string; generated_at: string; as_of: string; schema_version: number;
  model_hash: string; forward_model_hash: string | null; report_sha256: string;
  protocol_hash: string | null; comparison_group: string | null; state: string;
  events: number; pair_log_loss: number | null; brier: number | null; sg_rmse: number | null;
  simple_prior_log_loss: number | null; promotion_eligible: boolean;
  promotion_status: "research_only" | "eligible_for_review"; test_status: "exposed_retrospective" | "retrospective";
}
type RunHistoryReport = {
  schema_version: 1; state: "available" | "unavailable"; basis: string; latest_report_sha256: string;
  summary: { total_runs: number; displayed_runs: number; weeks_observed: number; comparable_groups: number; truncated: boolean };
  runs: Run[]; notes: string[];
}
const record = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v)
const finite = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v)
const nullableNumber = (v: unknown) => v === null || finite(v)
function readHistory(value: unknown): RunHistoryReport {
  if (!record(value) || value.schema_version !== 1 || !["available", "unavailable"].includes(String(value.state)) || !record(value.summary) || !["total_runs", "displayed_runs", "weeks_observed", "comparable_groups"].every(k => finite((value.summary as Record<string, unknown>)[k])) || !Array.isArray(value.runs) || !value.runs.every(r => record(r) && ["run_id", "generated_at", "model_hash", "report_sha256"].every(k => typeof r[k] === "string") && finite(r.events) && ["pair_log_loss", "brier", "sg_rmse", "simple_prior_log_loss"].every(k => nullableNumber(r[k])) && (r.comparison_group === null || typeof r.comparison_group === "string") && ["research_only", "eligible_for_review"].includes(String(r.promotion_status))) || !Array.isArray(value.notes) || !value.notes.every(n => typeof n === "string")) throw new Error("Run history is incomplete.")
  return value as unknown as RunHistoryReport
}

export function RunHistory() {
  const report = useQuery({ queryKey: ["learning-run-history"], queryFn: async ({ signal }) => readHistory(await getReadOnlyJson<unknown>("/reports/learning-history.json", signal)), staleTime: 60_000, retry: false })
  const r = report.data
  return <section className="lw-run-history" aria-label="Model run history"><div className="lw-section-header"><div><h2>Model runs</h2><p>Versioned evaluations and their recorded promotion status.</p></div><a className="lw-plain-link" href="/reports/learning-history.json" download><ArrowDownToLine size={14}/>Run history JSON</a></div>
    {report.isPending ? <p role="status">Reading dated model runs…</p> : report.isError || !r || r.state === "unavailable" || !r.runs.length ? <div className="lw-run-history-empty"><p>Longitudinal evidence is unavailable. Dated comparable runs are needed to measure improvement over time.</p><button className="lw-plain-link" onClick={() => void report.refetch()}><RefreshCw size={14}/>Reload run history</button></div> : <>
      <p className="lw-run-history-context">{number(r.summary.total_runs,0)} preserved runs · {number(r.summary.weeks_observed,0)} observed {r.summary.weeks_observed === 1 ? "week" : "weeks"}.{r.summary.weeks_observed < 2 ? " Same-day reruns do not show week-to-week improvement." : " Improvement requires comparisons on the same evaluation cohort."}{r.summary.comparable_groups > 1 ? ` These runs use ${r.summary.comparable_groups} comparison groups; scores across groups are not directly comparable.` : ""}</p>
      <div className="lw-table-scroll lw-mobile-table-wrap"><table className="lw-data-table lw-run-history-table lw-responsive-table" role="table"><thead role="rowgroup"><tr role="row"><th id="run-date" scope="col" role="columnheader">Generated / version</th><th id="run-cohort" scope="col" role="columnheader">Comparison group</th><th id="run-events" scope="col" role="columnheader">Events</th><th id="run-loss" scope="col" role="columnheader">Pair log loss</th><th id="run-prior" scope="col" role="columnheader">Simple prior</th><th id="run-brier" scope="col" role="columnheader">Brier</th><th id="run-status" scope="col" role="columnheader">Promotion</th></tr></thead><tbody role="rowgroup">{r.runs.map((run,index) => <tr key={run.run_id} role="row"><th id={`run-${index}`} scope="row" role="rowheader"><time dateTime={run.generated_at}>{shortDate(run.generated_at)}</time><small title={run.model_hash}>v{run.schema_version} · {run.model_hash.slice(0,12)}</small><small className="lw-run-id">{run.run_id}</small><small>{run.test_status === "exposed_retrospective" ? "Exposed retrospective audit" : "Retrospective evaluation"}</small></th><td role="cell" headers={`run-${index} run-cohort`}><span className="lw-cell-label" aria-hidden="true">Comparison group</span><code title={run.comparison_group ?? undefined}>{run.comparison_group?.slice(0,12) ?? "Unspecified"}</code></td><td role="cell" headers={`run-${index} run-events`}><span className="lw-cell-label" aria-hidden="true">Events</span><strong>{run.events}</strong></td><td role="cell" headers={`run-${index} run-loss`}><span className="lw-cell-label" aria-hidden="true">Pair log loss</span><strong>{number(run.pair_log_loss,4)}</strong></td><td role="cell" headers={`run-${index} run-prior`}><span className="lw-cell-label" aria-hidden="true">Simple prior log loss</span><strong>{number(run.simple_prior_log_loss,4)}</strong></td><td role="cell" headers={`run-${index} run-brier`}><span className="lw-cell-label" aria-hidden="true">Brier</span><strong>{number(run.brier,4)}</strong></td><td role="cell" headers={`run-${index} run-status`}><span className="lw-cell-label" aria-hidden="true">Promotion</span><strong>{run.promotion_status === "eligible_for_review" ? "Eligible for review" : "Research only"}</strong></td></tr>)}</tbody></table></div>
      {r.summary.truncated && <p className="lw-small lw-muted">Showing {r.summary.displayed_runs} of {r.summary.total_runs} preserved runs in this report.</p>}
      {r.notes.length > 0 && <ul className="lw-small lw-muted">{r.notes.map(note => <li key={note}>{note}</li>)}</ul>}
    </>}
  </section>
}
