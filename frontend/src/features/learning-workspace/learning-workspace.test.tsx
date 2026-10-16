import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import type { OperatorBoard } from "@/features/operator-data/operator-api"
import { LearningWorkspace } from "./learning-workspace"
import type { LearningReport, Metrics, PerformanceReport, PerformanceScope } from "./types"

vi.mock("@/components/theme-toggle", () => ({ ThemeToggle: () => null }))

const players = ["Alpha Player", "Bravo Player", "Charlie Player", "Delta Player", "Echo Player", "Foxtrot Player", "Golf Player", "Hotel Player"]
function board(overrides: Partial<OperatorBoard> = {}): OperatorBoard {
  return {
    schema_version: "operator-read-model/v1", track: "champion", mode: "upcoming", state: "fresh",
    reason: { code: "ready", message: "Published field" }, event: { event_id: "event-1", event_name: "Fixture Open", course_name: "Fixture Course" },
    source: { generated_at: "2026-10-14T12:00:00Z", age_seconds: 15 }, eligibility: { verified: true, observed_tour: "pga" },
    rankings: players.map((player, index) => ({ player, player_key: `player-${index}`, rank: index + 1, composite: 90 - index * 2,
      form: 60 + index, course_fit: 80 - index, momentum: 50 + index * 3, course_rounds: index, availability: { recent_rounds_count: 12 + index } })),
    leaderboard: [], picks: { matchups: [], value_bets: [] }, ...overrides,
  }
}
function learning(eventId = "event-1"): LearningReport {
  const evaluation = { events: 10, player_events: 500, pairs: 1200, pair_log_loss: 0.65, brier: 0.23, pair_accuracy: 0.6, rank_correlation: 0.4, sg_rmse: 1.1 }
  const split = { events: 10, player_events: 500, start: "2026-01-01", end: "2026-09-01", event_ids: ["fixture"] }
  return {
    schema_version: 1, generated_at: "2026-10-14T12:00:00Z", state: "research",
    candidate: { id: "sg", label: "SG fixture challenger", hash: "candidate-sha", method: "ridge", feature_names: [], ranking_unit: "expected_sg_per_round" },
    baseline: { id: "baseline", label: "Original model", hash: "baseline-sha", source_commit: "abc123", preserved: true, comparison_kind: "frozen_replay" },
    data: { rounds: 35000, player_events: 8000, events: 81, first_event: "2024-01-01", last_event: "2026-09-01", source_sha256: "source-sha" },
    splits: { train: split, validation: split, test: split }, selection: { objective: "validation log loss", trials: [{ ridge: 1, validation_log_loss: 0.65 }], selected_ridge: 1 },
    comparisons: { test: { candidate: evaluation, baseline: evaluation, naive: evaluation }, delta: {}, event_series: [] },
    promotion: { eligible: false, decision: "research", reasons: ["More later-event evidence needed."] },
    market_evidence: { state: "unavailable", quote_count: 0, clv_count: 0, roi_pct: null, avg_clv_pct: null, reason: "No matched closing quotes." },
    limitations: ["Retrospective research, not an untouched holdout."], current_event: { event_id: eventId },
    current_rankings: players.map((player_display, index) => ({ player_display, player_key: `player-${index}`, rank: players.length - index,
      expected_sg_per_round: index / 10, history_rounds: 30, last_observed: "2026-10-01", feature_coverage: 1 })),
  }
}
function metrics(decisions: number, profit: number): Metrics {
  return { decisions, events: 1, wins: decisions / 2, losses: decisions / 2, zero_return: 0, unit_profit: profit, unit_stake: decisions,
    unit_roi_pct: 100 * profit / decisions, max_drawdown_units: 2, brier: 0.24, log_loss: 0.67,
    probability_n: decisions, probability_coverage_pct: 100, clv_bps: null, closing_line_n: 0 }
}
function scope(decisions: number, profit: number, eventName: string): PerformanceScope {
  return { summary: metrics(decisions, profit), interval: { method: "event_cluster_percentile_bootstrap", unit_roi_pct_95: null, brier_95: null, events: 1, replicates: 0 },
    series: [{ event_key: eventName, event_name: eventName, event_start: "2026-09-01", event_end: "2026-09-04", decisions, unit_profit: profit,
      unit_roi_pct: 100 * profit / decisions, cumulative_profit: profit, drawdown_units: 0, brier: 0.24, probability_n: decisions }],
    monthly: [{ month: "2026-09", decisions, unit_profit: profit, unit_roi_pct: 100 * profit / decisions }],
    reliability: [{ lower: 0.5, upper: 0.6, n: decisions, predicted: 0.55, observed: 0.5 }],
    models: [{ key: "baseline", ...metrics(decisions, profit) }], books: [{ key: "fixturebook", ...metrics(decisions, profit) }] }
}
function performance(): PerformanceReport {
  const scopes: Record<string, PerformanceScope> = {}
  for (const cohort of ["pre_event", "paper"]) for (const lane of ["all", "dashboard", "lab"]) for (const market of ["all", "72h", "top20"]) {
    const selections = cohort === "paper" ? 40 : lane === "lab" ? 12 : market === "72h" ? 6 : 10
    scopes[`${cohort}|${lane}|${market}`] = scope(selections, cohort === "paper" ? -4 : lane === "lab" ? 3 : market === "72h" ? -1 : 2, `${cohort}-${lane}-${market} event`)
  }
  return { schema_version: 1, as_of: "2026-10-14", basis: "stored_paper_records", default_cohort: "pre_event",
    dimensions: { markets: ["72h", "top20"], lanes: ["dashboard", "lab"], models: ["baseline"], books: ["fixturebook"] },
    cohorts: { pre_event: { label: "Before the event" }, paper: { label: "Inclusive paper record" } }, scopes, provenance: {},
    caveats: ["Retrospective model selections, not verified placed bets."] }
}

const clients: QueryClient[] = []
let boardPayload: OperatorBoard
let learningPayload: unknown
let performancePayload: PerformanceReport
let coveragePayload: unknown
let historyPayload: unknown
const coverage = () => ({ schema_version: 1, state: "recovered_source_inventory", as_of: "2026-10-15", summary: { complete_card_versions: 233, named_event_labels: 30, indexed_observations: 12707, payloads_with_observations: 355 }, events: [{ label: "Recovered Fixture Open", card_versions: 4, first_generated: "2026-03-01", last_generated: "2026-03-04", observations: 200, status: "publication_unverified" }], gaps: ["Source publication timing is unverified."], basis: "Preserved original source payloads" })
let fetchMock: ReturnType<typeof vi.fn>
function renderWorkspace(route = "/") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  clients.push(client)
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[route]}><LearningWorkspace /></MemoryRouter></QueryClientProvider>)
}
beforeEach(() => {
  boardPayload = board()
  learningPayload = learning()
  performancePayload = performance()
  coveragePayload = coverage()
  historyPayload = { schema_version: 1, state: "available", basis: "Preserved model runs", latest_report_sha256: "latest-sha", summary: { total_runs: 2, displayed_runs: 2, weeks_observed: 1, comparable_groups: 2, truncated: false }, runs: [15,16].map(day => ({ run_id: `run-${day}`, generated_at: `2026-10-${day}T12:00:00Z`, as_of: `2026-10-${day}`, schema_version: day === 15 ? 1 : 2, model_hash: `model-${day}-hash`, forward_model_hash: null, report_sha256: `report-${day}`, protocol_hash: `protocol-${day}`, comparison_group: `group-${day}`, state: "evaluated", events: 10, pair_log_loss: 0.65, brier: 0.23, sg_rmse: 1.1, simple_prior_log_loss: 0.69, promotion_eligible: false, promotion_status: "research_only", test_status: "exposed_retrospective" })), notes: ["Cross-protocol metrics are not an improvement series."] }
  fetchMock = vi.fn().mockImplementation(async (input: string) => {
    const url = String(input)
    if (url.startsWith("/api/desk/board")) return { ok: true, json: async () => boardPayload }
    if (url === "/reports/learning-latest.json") return { ok: true, json: async () => learningPayload }
    if (url === "/reports/performance-2026.json") return { ok: true, json: async () => performancePayload }
    if (url === "/reports/learning-history.json") return { ok: true, json: async () => historyPayload }
    if (url === "/reports/history-coverage.json") return { ok: true, json: async () => coveragePayload }
    if (url === "/api/autoresearch/settings") return { ok: true, json: async () => ({ autoresearch_effort: "standard", optuna_trials_per_cycle: 10 }) }
    throw new Error(`Unexpected test request: ${url}`)
  })
  vi.stubGlobal("fetch", fetchMock)
})
afterEach(() => {
  cleanup()
  clients.splice(0).forEach(client => client.clear())
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe("rankings workspace", () => {
  it("opens the full original field by default and selects a player without changing the published ranking", async () => {
    const user = userEvent.setup()
    renderWorkspace()
    const field = await screen.findByRole("region", { name: "Full field rankings" })
    await within(field).findByRole("button", { name: "Hotel Player" })
    expect(within(field).getAllByRole("row")).toHaveLength(players.length + 1)
    expect(screen.getByRole("combobox", { name: "Ranking model" })).toHaveValue("baseline")
    await user.click(within(field).getByRole("button", { name: "Hotel Player" }))
    const detail = screen.getByRole("complementary", { name: "Selected player details" })
    expect(within(detail).getByRole("heading", { name: "Hotel Player" })).toBeInTheDocument()
    expect(within(detail).getByText("#8 in this field")).toBeInTheDocument()
    expect(within(detail).getByRole("link", { name: "Full player profile" })).toHaveAttribute("href", "/players/player-7")
    expect(within(detail).getByRole("link", { name: "Find Player markets" })).toHaveAttribute("href", "/markets?mode=upcoming&q=Hotel%20Player")
  })

  it("searches the full field and sorts component scores without truncating or changing their values", async () => {
    const user = userEvent.setup()
    renderWorkspace("/rankings")
    const table = await screen.findByRole("table")
    await within(table).findByRole("button", { name: "Hotel Player" })
    await user.click(within(table).getByRole("button", { name: "Form" }))
    expect(within(table).getAllByRole("row")[1]).toHaveTextContent("Hotel Player")
    expect(within(table).getAllByRole("row")[1]).toHaveTextContent("67.0")
    await user.type(screen.getByRole("textbox", { name: "Search the field" }), "golf")
    expect(within(table).getAllByRole("row")).toHaveLength(2)
    expect(within(table).getByRole("button", { name: "Golf Player" })).toBeInTheDocument()
    await user.clear(screen.getByRole("textbox", { name: "Search the field" }))
    expect(within(table).getAllByRole("row")).toHaveLength(players.length + 1)
  })

  it("offers the challenger only when its event identity matches and preserves original composite components", async () => {
    const user = userEvent.setup()
    renderWorkspace()
    const table = await screen.findByRole("table")
    await waitFor(() => expect(screen.getByRole("option", { name: "SG challenger" })).not.toBeDisabled())
    await user.selectOptions(screen.getByRole("combobox", { name: "Ranking model" }), "challenger")
    expect(within(table).getAllByRole("row")[1]).toHaveTextContent("Hotel Player")
    expect(within(table).getAllByRole("row")[1]).toHaveTextContent("+0.70")
    expect(screen.getByText(/Shadow projection in expected SG per round.*8 of 8 players projected/)).toBeInTheDocument()
    await user.click(within(table).getByRole("button", { name: "Exp. SG" }))
    expect(screen.getByRole("combobox", { name: "Ranking model" })).toHaveValue("challenger")
    expect(within(table).getAllByRole("row")[1]).toHaveTextContent("Hotel Player")
    await user.click(within(table).getByRole("button", { name: "Exp. SG" }))
    expect(within(table).getAllByRole("row")[1]).toHaveTextContent("Alpha Player")
    await user.selectOptions(screen.getByRole("combobox", { name: "Ranking model" }), "baseline")
    expect(within(table).getAllByRole("row")[1]).toHaveTextContent("Hotel Player")
    await user.click(within(table).getByRole("button", { name: "Rank" }))
    expect(within(table).getAllByRole("row")[1]).toHaveTextContent("Alpha Player")
    expect(within(table).getAllByRole("row")[1]).toHaveTextContent("90.0")
  })

  it.each(["another-event", ""])("withholds candidate projections for mismatched or absent event identity (%s)", async eventId => {
    learningPayload = learning(eventId)
    renderWorkspace()
    await screen.findByRole("table")
    await waitFor(() => expect(clients.at(-1)!.getQueryData(["learning-report"])).toBeTruthy())
    expect(screen.getByRole("option", { name: "SG challenger · no matching field" })).toBeDisabled()
    expect(screen.queryByText("+0.70")).not.toBeInTheDocument()
  })

  it("uses an explicit in-play empty state and can return to the upcoming full field", async () => {
    const user = userEvent.setup()
    boardPayload = board({ mode: "live", rankings: [], state: "empty", event: {}, reason: { code: "no_live_event", message: "No live event published" } })
    renderWorkspace("/?mode=live")
    expect(await screen.findByRole("heading", { name: "No event is in play." })).toBeInTheDocument()
    expect(screen.queryByRole("table")).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: "View upcoming field" })).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("mode=live"))).toBe(true)
    boardPayload = board()
    await user.click(screen.getByRole("button", { name: "View upcoming field" }))
    const table = await screen.findByRole("table")
    expect(within(table).getAllByRole("row")).toHaveLength(players.length + 1)
    expect(screen.getByRole("option", { name: "SG challenger" })).not.toBeDisabled()
  })

  it("withholds a failed source's retained rows instead of presenting them as published rankings", async () => {
    boardPayload = board({ state: "unavailable", reason: { code: "unverified_event", message: "Event identity could not be verified" } })
    renderWorkspace()
    await screen.findByRole("heading", { name: "Fixture Open" })
    expect(screen.queryByRole("table")).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Alpha Player" })).not.toBeInTheDocument()
    expect(screen.getByText("Event identity could not be verified")).toBeInTheDocument()
  })
})

describe("performance scope consistency", () => {
  it("uses the same selected cohort, model lane and market in its chart, totals and event ledger", async () => {
    const user = userEvent.setup()
    renderWorkspace("/performance")
    await screen.findByRole("heading", { name: "The event record" })
    const ledger = () => within(screen.getByRole("heading", { name: "The event record" }).closest("section")!)
    const selections = () => screen.getByText("Settled selections").parentElement!
    expect(ledger().getByRole("rowheader", { name: /pre_event-dashboard-all event/ })).toBeInTheDocument()
    expect(within(selections()).getByText("10")).toBeInTheDocument()
    expect(screen.getByRole("img", { name: /Cumulative paper return across 1 events, ending at \+2.0 units/ })).toBeInTheDocument()

    await user.selectOptions(screen.getByRole("combobox", { name: "Performance market" }), "72h")
    expect(ledger().getByRole("rowheader", { name: /pre_event-dashboard-72h event/ })).toBeInTheDocument()
    expect(ledger().queryByRole("rowheader", { name: /pre_event-dashboard-all event/ })).not.toBeInTheDocument()
    expect(within(selections()).getByText("6")).toBeInTheDocument()
    expect(screen.getByRole("img", { name: /ending at -1.0 units/ })).toBeInTheDocument()

    await user.selectOptions(screen.getByRole("combobox", { name: "Performance model lane" }), "lab")
    expect(ledger().getByRole("rowheader", { name: /pre_event-lab-72h event/ })).toBeInTheDocument()
    expect(within(selections()).getByText("12")).toBeInTheDocument()
    expect(screen.getByRole("img", { name: /ending at \+3.0 units/ })).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "All settled paper" }))
    expect(ledger().getByRole("rowheader", { name: /paper-lab-72h event/ })).toBeInTheDocument()
    expect(within(selections()).getByText("40")).toBeInTheDocument()
    expect(screen.getByRole("img", { name: /ending at -4.0 units/ })).toBeInTheDocument()
    expect(screen.getByText(/including records captured during or after events/)).toBeInTheDocument()
    expect(screen.getByText("Unavailable")).toBeInTheDocument()
    expect(fetchMock.mock.calls.filter(([url]) => url === "/reports/performance-2026.json")).toHaveLength(1)
    expect(fetchMock.mock.calls.some(([url]) => url === "/reports/history-coverage.json")).toBe(true)
  })

  it("clears the chart and previous metrics when a selected scope is absent", async () => {
    delete performancePayload.scopes["pre_event|dashboard|72h"]
    const user = userEvent.setup()
    renderWorkspace("/performance")
    await screen.findByRole("heading", { name: "The event record" })
    await user.selectOptions(screen.getByRole("combobox", { name: "Performance market" }), "72h")
    expect(screen.getByRole("alert")).toHaveTextContent("This report is unavailable.")
    expect(screen.queryByRole("heading", { name: "The event record" })).not.toBeInTheDocument()
    expect(screen.queryByRole("img", { name: /Cumulative paper return/ })).not.toBeInTheDocument()
    expect(screen.queryByText("Settled selections")).not.toBeInTheDocument()
  })
})

describe("source and report safeguards", () => {
  it.each([
    { verified: false },
    { verified: true, field_event_id: "different-event" },
  ])("withholds rows when field membership is unverified or attached to another event (%j)", async eligibility => {
    boardPayload = board({ eligibility })
    renderWorkspace()
    expect(await screen.findByRole("heading", { name: "The field needs verification." })).toBeInTheDocument()
    expect(screen.queryByRole("table")).not.toBeInTheDocument()
    expect(screen.getByRole("option", { name: "SG challenger · no matching field" })).toBeDisabled()
  })

  it("labels field verification as membership and shows missing research forecasts without inventing projections", async () => {
    const payload = learning()
    payload.current_rankings = payload.current_rankings.slice(1)
    learningPayload = payload
    boardPayload = board({ eligibility: { verified: true, field_event_id: "event-1", field_player_count: 8 } })
    const user = userEvent.setup()
    renderWorkspace()
    await waitFor(() => expect(screen.getByRole("option", { name: "SG challenger" })).not.toBeDisabled())
    expect(screen.getByText(/This verifies field membership, not prices or model accuracy/)).toBeInTheDocument()
    await user.selectOptions(screen.getByRole("combobox", { name: "Ranking model" }), "challenger")
    expect(screen.getByText(/7 of 8 players projected/)).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Alpha Player" }))
    const detail = screen.getByRole("complementary", { name: "Selected player details" })
    expect(within(detail).getByText("#— in this field")).toBeInTheDocument()
    expect(within(detail).getByRole("img")).toHaveAttribute("aria-label", expect.stringContaining("expected SG per round — compared with 7"))
  })

  it("puts compact player details before the field and returns focus to the selected row", async () => {
    const original = window.matchMedia
    vi.spyOn(window, "matchMedia").mockImplementation(query => ({ ...original(query), matches: query.includes("max-width: 1050px") }))
    const user = userEvent.setup()
    renderWorkspace()
    const row = await screen.findByRole("button", { name: "Hotel Player" })
    const detail = document.querySelector<HTMLElement>(".lw-player-aside")!
    const field = screen.getByRole("region", { name: "Full field rankings" })
    expect(detail.compareDocumentPosition(field) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(within(detail).queryByRole("heading", { name: "Alpha Player" })).not.toBeInTheDocument()
    expect(detail).toHaveAttribute("hidden")
    expect(screen.getByRole("button", { name: "View Alpha Player details" })).toHaveAttribute("aria-expanded", "false")
    await user.click(row)
    expect(within(detail).getByRole("heading", { name: "Hotel Player" })).toBeVisible()
    expect(within(detail).getByText("Back to rankings").closest("button")!).toHaveAttribute("aria-expanded", "true")
    await user.click(within(detail).getByText("Back to rankings").closest("button")!)
    expect(row).toHaveFocus()
    expect(within(detail).queryByRole("heading", { name: "Hotel Player" })).not.toBeInTheDocument()
  })

  it("renders an insufficient-data report as coverage while keeping the original model accessible", async () => {
    learningPayload = { schema_version: 1, state: "insufficient_data", data: { rounds: 200, player_events: 7, events: 2 }, promotion: { reasons: ["Too few eligible events."] }, comparisons: { test: {} } }
    renderWorkspace("/models")
    expect(await screen.findByRole("heading", { name: "More history is needed." })).toBeInTheDocument()
    expect(screen.getByText("200 source rounds · 7 eligible player-events · 2 eligible events")).toBeInTheDocument()
    expect(screen.getByText("Too few eligible events.")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: /Open original model/ })).toHaveAttribute("href", "/research/legacy-model")
    expect(screen.queryByRole("heading", { name: "Same events. Same player pairs." })).not.toBeInTheDocument()
  })

  it.each([null, {}, { schema_version: 1, state: "error" }, { ...learning(), current_rankings: {} }, { ...learning(), comparisons: { test: {} } }])("handles malformed learning reports without rendering a comparison (%j)", async payload => {
    learningPayload = payload
    renderWorkspace("/models")
    expect(await screen.findByRole("alert")).toHaveTextContent("The training report is unavailable.")
    expect(screen.getByRole("link", { name: /Open original model/ })).toBeInTheDocument()
    expect(screen.queryByRole("heading", { name: "Same events. Same player pairs." })).not.toBeInTheDocument()
  })

  it("labels raw source rounds separately from eligible training examples", async () => {
    renderWorkspace("/models")
    await screen.findByRole("heading", { name: "SG fixture challenger" })
    const source = screen.getByText("Source rounds").parentElement!
    const eligible = screen.getByText("Eligible player-events").parentElement!
    expect(source).toHaveTextContent("35,000")
    expect(eligible).toHaveTextContent("8,000")
    expect(screen.queryByText("Training corpus")).not.toBeInTheDocument()
    expect(screen.getAllByText(/not an untouched holdout/).length).toBeGreaterThan(0)
  })

  it("keeps preserved-source coverage distinct from the selected reconciled performance cohort", async () => {
    const user = userEvent.setup()
    renderWorkspace("/performance")
    const history = await screen.findByRole("region", { name: "Recovered source coverage" })
    expect(history).toHaveTextContent("233 card versions across 30 named event labels.")
    expect(history).toHaveTextContent("performance record below uses only the selected reconciled cohort")
    await user.click(within(history).getByText("Browse recovered event labels"))
    expect(within(history).getByRole("rowheader", { name: "Recovered Fixture Open" })).toBeVisible()
    expect(within(history).getByRole("link", { name: "Download source coverage" })).toHaveAttribute("href", "/reports/history-coverage.json")
    await screen.findByRole("heading", { name: "The event record" })
    expect(screen.getByText("Settled selections").parentElement).toHaveTextContent("10")
  })

  it("keeps performance usable when recovered-source coverage is malformed", async () => {
    coveragePayload = { schema_version: 1, events: {} }
    renderWorkspace("/performance")
    expect(await screen.findByText(/Recovered source coverage is unavailable/)).toBeInTheDocument()
    expect(await screen.findByRole("heading", { name: "The event record" })).toBeInTheDocument()
  })
})


describe("versioned forward projections", () => {
  function v2(): LearningReport {
    const r = learning()
    r.schema_version = 2
    r.candidate.trained_through = "2025-12-14"
    r.current_event = { event_id: "event-1", tour: "pga", year: 2026, calendar_start: "2026-10-15", snapshot_generated_at: "2026-10-14T12:00:00Z", state: "resolved", identity_basis: "unique_calendar_within_dated_snapshot_window" }
    r.forward_candidate = { hash: "forward-model-sha", evaluated_hash: r.candidate.hash, role: "forward_shadow_only_not_used_in_audit", trained_through: "2026-10-11" }
    r.current_rankings_model_hash = r.forward_candidate.hash
    r.protocol = { test_status: "exposed_retrospective_2026_audit" }
    r.comparisons.test.baseline_calibrated = { ...r.comparisons.test.baseline }
    return r
  }
  it("binds current projections to their forward refit and labels its separate training cutoff", async () => {
    learningPayload = v2()
    const user = userEvent.setup()
    renderWorkspace()
    await waitFor(() => expect(screen.getByRole("option", { name: "SG challenger" })).not.toBeDisabled())
    await user.selectOptions(screen.getByRole("combobox", { name: "Ranking model" }), "challenger")
    expect(screen.getByText(/Forward refit through Oct 11, 2026 · model forward-mode/)).toBeInTheDocument()
  })
  it.each(["wrong-forward-hash", undefined])("withholds unbound v2 current rankings (%s) while preserving the original field", async hash => {
    const payload = v2()
    payload.current_rankings_model_hash = hash
    learningPayload = payload
    renderWorkspace()
    await screen.findByRole("table")
    await waitFor(() => expect(clients.at(-1)!.getQueryData(["learning-report"])).toBeTruthy())
    expect(screen.getByRole("option", { name: "SG challenger · no matching field" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "Hotel Player" })).toBeInTheDocument()
  })
  it.each([
    { label: "wrong tour", change: { tour: "dpwt" } },
    { label: "year inconsistent with calendar", change: { year: 2025 } },
    { label: "calendar from another year", change: { calendar_start: "2025-10-15" } },
    { label: "invalid calendar date", change: { calendar_start: "2026-02-30" } },
    { label: "wrong capture", change: { snapshot_generated_at: "2026-10-13T12:00:00Z" } },
    { label: "equivalent capture with different bytes", change: { snapshot_generated_at: "2026-10-14T12:00:00+00:00" } },
    { label: "missing capture", change: { snapshot_generated_at: undefined } },
    { label: "unresolved field", change: { state: "withheld" } },
  ])("withholds the same event ID when its v2 cohort has $label", async ({ change }) => {
    const payload = v2()
    payload.current_event = { ...payload.current_event, ...change }
    learningPayload = payload
    renderWorkspace()
    await screen.findByRole("table")
    await waitFor(() => expect(clients.at(-1)!.getQueryData(["learning-report"])).toBeTruthy())
    expect(screen.getByRole("option", { name: "SG challenger · no matching field" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "Hotel Player" })).toBeInTheDocument()
  })
  it.each([
    { label: "another explicit board year", identity: { year: 2025 }, available: false },
    { label: "matching explicit board year", identity: { year: 2026 }, available: true },
    { label: "explicit board tour overrides observed tour", identity: { tour: "dpwt" }, available: false },
    { label: "matching explicit board tour", identity: { tour: "pga" }, available: true },
  ])("respects $label for a recurring event ID", async ({ identity, available }) => {
    learningPayload = v2()
    boardPayload = board({ event: { event_id: "event-1", event_name: "Fixture Open", ...identity } })
    renderWorkspace()
    await screen.findByRole("table")
    await waitFor(() => expect(clients.at(-1)!.getQueryData(["learning-report"])).toBeTruthy())
    const option = screen.getByRole("option", { name: available ? "SG challenger" : "SG challenger · no matching field" })
    if (available) expect(option).not.toBeDisabled()
    else expect(option).toBeDisabled()
  })
  it("keeps the evaluated model cutoff and calibrated baseline beside the retrospective audit", async () => {
    learningPayload = v2()
    renderWorkspace("/models")
    await screen.findByRole("heading", { name: "SG fixture challenger" })
    expect(screen.getByText("Evaluated model trained through").parentElement).toHaveTextContent("Dec 14, 2025")
    expect(screen.getByRole("columnheader", { name: "PIT replay · calibrated before 2026" })).toBeInTheDocument()
    expect(screen.getByText(/The 2026 audit is exposed retrospective evidence/)).toBeInTheDocument()
    expect(screen.queryByText(/Forward refit through/)).not.toBeInTheDocument()
  })
})


describe("readable model and event evidence", () => {
  it("keeps every benchmark value associated with its measure and model, with mobile labels", async () => {
    renderWorkspace("/models")
    const metric = await screen.findByRole("rowheader", { name: /Pair log loss/ })
    const row = metric.closest("tr")!
    const cells = within(row).getAllByRole("cell")
    expect(cells).toHaveLength(3)
    for (const cell of cells) {
      const ids = cell.getAttribute("headers")!.split(" ")
      expect(ids).toContain(metric.id)
      expect(ids.every(id => !!document.getElementById(id))).toBe(true)
      expect(cell.querySelector(".lw-cell-label")).toBeInTheDocument()
      expect(cell.querySelector("strong")).toHaveTextContent("0.6500")
    }
    const windows = screen.getByRole("region", { name: "Chronological evaluation windows" })
    expect(windows).toHaveTextContent("Jan 1, 2026 – Sep 1, 2026")
    expect(screen.getByText("Report generated").parentElement).toHaveTextContent("Oct 14, 2026")
    expect(screen.queryByText("Player insight")).not.toBeInTheDocument()
  })

  it("keeps the event's paper return and outcome labels with the event on compact layouts", async () => {
    renderWorkspace("/performance")
    const event = await screen.findByRole("rowheader", { name: /pre_event-dashboard-all event/ })
    const row = event.closest("tr")!
    const cell = row.querySelector('[headers="event-0 event-return"]')!
    expect(cell).toHaveTextContent("Paper return+2.0u")
    expect(row.querySelector('[headers="event-0 event-roi"]')).toHaveTextContent("Paper ROI+20.0%")
    expect(event).toHaveTextContent("Sep 1, 2026")
    expect(document.getElementById("event-return")).toHaveTextContent("Paper return")
  })

  it("shows dated run versions, cohorts and promotion status without implying same-week improvement", async () => {
    renderWorkspace("/models")
    const history = await screen.findByRole("region", { name: "Model run history" })
    await within(history).findByText(/Same-day reruns do not show week-to-week improvement/)
    expect(history).toHaveTextContent("2 preserved runs · 1 observed week")
    expect(history).toHaveTextContent("scores across groups are not directly comparable")
    expect(within(history).getByRole("rowheader", { name: /Oct 15, 2026.*v1.*model-15-has/ })).toBeInTheDocument()
    expect(within(history).getByRole("rowheader", { name: /Oct 16, 2026.*v2.*model-16-has/ })).toBeInTheDocument()
    expect(within(history).getAllByText("Research only")).toHaveLength(2)
    expect(within(history).getByRole("link", { name: "Run history JSON" })).toHaveAttribute("href", "/reports/learning-history.json")
  })

  it("states missing longitudinal evidence without hiding the current evaluation", async () => {
    historyPayload = { schema_version: 1, state: "available", runs: {} }
    renderWorkspace("/models")
    expect(await screen.findByText(/Longitudinal evidence is unavailable/)).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "Same events. Same player pairs." })).toBeInTheDocument()
  })
})
