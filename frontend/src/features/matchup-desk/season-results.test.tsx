import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { MatchupDesk } from "./matchup-desk"
import { SEASON_DECISIONS_PATH, SEASON_REPORT_PATH, SeasonResults, type SeasonReport } from "./season-results"

const { readJson, getBoard } = vi.hoisted(() => ({ readJson: vi.fn(), getBoard: vi.fn() }))
vi.mock("@/features/operator-data/operator-api", () => ({ getReadOnlyJson: readJson, getDeskBoard: getBoard }))
vi.mock("@/components/theme-toggle", () => ({ ThemeToggle: () => null }))

const fixture: SeasonReport = {
  schema_version: 1, as_of: "2026-10-14", basis: "stored_paper_records",
  coverage: { source_generations: 22, core_observations: 200, pick_observations: 150, decision_groups: 90, calendar_elapsed_events: 3, events_with_picks: 2, events_with_cards: 2, unresolved_events: 1, conflict_groups: 4, incomplete_contract_groups: 20, selection_eligible: 5, unreadable_sources: 2, salvaged_observations: 0 },
  markets: [
    { key: "72h", label: "72-hole matchups", lanes: [
      { lane: "dashboard", records: 50, events: 2, wins: 20, losses: 10, zero_return: 2, void: 1, ungraded: 10, conflicts: 4, incomplete: 3, settled: 33, profit: 4.5, stake: 30, roi: .15, selection_eligible: 5 },
      { lane: "lab", records: 20, events: 1, wins: 4, losses: 6, zero_return: 0, void: 0, ungraded: 10, conflicts: 0, incomplete: 0, settled: 10, profit: -2, stake: 10, roi: -.2, selection_eligible: 0 },
    ] },
    { key: "18h", label: "18-hole matchups", lanes: [
      { lane: "dashboard", records: 20, events: 1, wins: 0, losses: 0, zero_return: 0, void: 0, ungraded: 0, conflicts: 0, incomplete: 20, missing_round: 20, settled: 0, profit: null, stake: null, roi: null, selection_eligible: 0 },
    ] },
  ],
  events: [
    { key: "sony", name: "Sony Open", starts_on: "2026-01-15", ends_on: "2026-01-18", state: "elapsed", records: 40, cards: 2, conflicts: 4, incomplete: 0, selection_eligible: 5, markets: [{ key: "72h", records: 40 }], source_url: "https://pgatourmedia.pgatourhq.com/tours/2026/pgatour/sonyopeninhawaii" },
    { key: "american", name: "The American Express", starts_on: "2026-01-22", ends_on: "2026-01-25", state: "elapsed", records: 50, cards: 1, conflicts: 0, incomplete: 20, selection_eligible: 0, markets: [{ key: "72h", records: 30 }, { key: "18h", records: 20 }] },
    { key: "missing", name: "Missing Open", starts_on: "2026-02-05", ends_on: "2026-02-08", state: "elapsed", records: 0, cards: 0, conflicts: 0, incomplete: 0, selection_eligible: 0, markets: [] },
    { key: "future", name: "Future Open", starts_on: "2026-11-05", ends_on: "2026-11-08", state: "upcoming", records: 0, cards: 0, conflicts: 0, incomplete: 0, selection_eligible: 0, markets: [] },
  ],
  issues: [{ key: "missing_round", label: "Round number missing", count: 20 }],
  selection: { status: "insufficient", minimum_earlier_events: 8, minimum_later_events: 5, minimum_later_decisions: 30, message: "Too few eligible events for reliable selection research.", rules: [
    { id: "baseline", label: "All eligible quotes", lane: "dashboard", market: "72h", model_variant: "baseline", eligible_decisions: 5, eligible_events: 3, earlier_events: 2, later_events: 1, later_decisions: 5, later_roi: .1, roi_interval: null, sufficient: false },
    { id: "baseline", label: "All eligible quotes", lane: "dashboard", market: "72h", model_variant: "v5", eligible_decisions: 2, eligible_events: 2, earlier_events: 1, later_events: 1, later_decisions: 2, later_roi: -.15, roi_interval: null, sufficient: false },
    { id: "baseline", label: "All eligible quotes", lane: "lab", market: "72h", model_variant: "baseline", eligible_decisions: 5, eligible_events: 3, earlier_events: 2, later_events: 1, later_decisions: 3, later_roi: null, roi_interval: null, sufficient: false },
  ] },
  caveats: ["Repeated source copies are preserved and reconciled without counting them as new picks."],
  provenance: { report_id: "test-fixture", source_manifest_sha256: "source-hash", calendar_sha256: "calendar-hash" },
}

const clients: QueryClient[] = []
function renderPage(route?: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  clients.push(client)
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[route || "/evidence"]}>{route ? <MatchupDesk /> : <SeasonResults />}</MemoryRouter></QueryClientProvider>)
}
beforeEach(() => {
  localStorage.clear()
  readJson.mockReset().mockResolvedValue(fixture)
  getBoard.mockReset()
})
afterEach(() => {
  cleanup()
  clients.splice(0).forEach(client => client.clear())
  vi.restoreAllMocks()
})

describe("season record", () => {
  it("opens the season report by default without current-store or board requests", async () => {
    renderPage("/evidence")
    expect(await screen.findByText("Stored paper records.")).toBeInTheDocument()
    expect(readJson).toHaveBeenCalledTimes(1)
    expect(readJson).toHaveBeenCalledWith(SEASON_REPORT_PATH, expect.any(AbortSignal))
    expect(getBoard).not.toHaveBeenCalled()
    expect(screen.getByRole("link", { name: "Season record" })).toHaveAttribute("aria-current", "page")
    expect(screen.getByRole("link", { name: /Report JSON/ })).toHaveAttribute("href", SEASON_REPORT_PATH)
    expect(screen.getByRole("link", { name: /Audit rows CSV/ })).toHaveAttribute("href", SEASON_DECISIONS_PATH)
    expect(screen.getByText("Snapshot Oct 14, 2026")).toBeInTheDocument()
  })

  it("keeps incomplete contracts visible without fabricating a return", async () => {
    renderPage()
    const button = await screen.findByRole("button", { name: "18-hole matchups" })
    const row = within(button.closest("tr")!)
    expect(row.getByText("20 / 0")).toBeInTheDocument()
    expect(row.getByText("—")).toBeInTheDocument()
    expect(row.getByText("— ROI · 0 settled")).toBeInTheDocument()
    expect(row.queryByText(/0\.00u|0\.0%/)).not.toBeInTheDocument()
    expect(screen.getByText("No rule promoted")).toBeInTheDocument()
  })

  it("separates Dashboard and Lab results and absent lanes", async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText("+4.50u")
    expect(screen.getByText("+15.0% ROI · 33 settled")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Lab" }))
    expect(screen.getByText("-2.00u")).toBeInTheDocument()
    expect(screen.getByText("-20.0% ROI · 10 settled")).toBeInTheDocument()
    expect(screen.queryByText("+4.50u")).not.toBeInTheDocument()
    expect(screen.getByText("No records in this lane")).toBeInTheDocument()
    expect(readJson).toHaveBeenCalledTimes(1)
  })

  it("scopes selection research to the selected market and lane without claiming a promoted rule", async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(await screen.findByText("Inspect 1 fixed rule"))
    let comparison = screen.getByRole("table", { name: /Fixed selection rules/ })
    expect(within(comparison).getByText("+10.0%")).toBeInTheDocument()
    expect(within(comparison).getByText("Interval unavailable")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Lab" }))
    await user.click(screen.getByText("Inspect 1 fixed rule"))
    comparison = screen.getByRole("table", { name: /Fixed selection rules/ })
    expect(within(comparison).queryByText("+10.0%")).not.toBeInTheDocument()
    expect(within(comparison).getByText("—")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "18-hole matchups" }))
    expect(screen.queryByRole("table", { name: /Fixed selection rules/ })).not.toBeInTheDocument()
    expect(screen.getByText("No rule comparison is available for this market and model lane.")).toBeInTheDocument()
    expect(screen.getByText("No rule promoted")).toBeInTheDocument()
  })

  it("compares one model version at a time even when rule IDs repeat", async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(await screen.findByText("Inspect 1 fixed rule"))
    let comparison = screen.getByRole("table", { name: /Fixed selection rules/ })
    expect(within(comparison).getAllByText("All eligible quotes")).toHaveLength(1)
    expect(within(comparison).getByText("+10.0%")).toBeInTheDocument()
    expect(within(comparison).queryByText("-15.0%")).not.toBeInTheDocument()
    await user.selectOptions(screen.getByRole("combobox", { name: "Selection research model version" }), "v5")
    await user.click(screen.getByText("Inspect 1 fixed rule"))
    comparison = screen.getByRole("table", { name: /Fixed selection rules/ })
    expect(screen.getByRole("heading", { name: "72-hole matchups · Dashboard · v5" })).toBeInTheDocument()
    expect(within(comparison).getByText("-15.0%")).toBeInTheDocument()
    expect(within(comparison).queryByText("+10.0%")).not.toBeInTheDocument()
    expect(within(comparison).getAllByText("All eligible quotes")).toHaveLength(1)
    await user.click(screen.getByRole("button", { name: "Lab" }))
    await user.click(screen.getByText("Inspect 1 fixed rule"))
    comparison = screen.getByRole("table", { name: /Fixed selection rules/ })
    expect(screen.getByRole("combobox", { name: "Selection research model version" })).toHaveValue("baseline")
    expect(within(comparison).queryByText("-15.0%")).not.toBeInTheDocument()
    expect(readJson).toHaveBeenCalledTimes(1)
  })

  it("keeps insufficient rule comparisons collapsed and distinguishes report-wide eligibility from the selected scope", async () => {
    const user = userEvent.setup()
    renderPage()
    const disclosure = await screen.findByText("Inspect 1 fixed rule")
    expect(disclosure.closest("details")).not.toHaveAttribute("open")
    expect(screen.getByRole("table", { name: /Fixed selection rules/ })).not.toBeVisible()
    expect(screen.getAllByText("No rule promoted")).toHaveLength(1)
    expect(screen.getByText("Report-wide:").parentElement).toHaveTextContent("5 eligible records across all markets, model lanes and versions")
    expect(screen.getByText("Selected scope:").parentElement).toHaveTextContent("5 eligible records across 3 events. Requires at least 8 earlier events, 5 later events and 30 later decisions")
    await user.selectOptions(screen.getByRole("combobox", { name: "Selection research model version" }), "v5")
    expect(screen.getByText("Selected scope:").parentElement).toHaveTextContent("2 eligible records across 2 events")
  })

  it("changes the same market scope from the local coverage and research controls", async () => {
    const user = userEvent.setup()
    renderPage()
    await user.selectOptions(await screen.findByRole("combobox", { name: "Event coverage market" }), "18h")
    expect(screen.getByRole("combobox", { name: "Selection research market" })).toHaveValue("18h")
    expect(screen.getByRole("button", { name: "18-hole matchups" })).toHaveAttribute("aria-pressed", "true")
    await user.selectOptions(screen.getByRole("combobox", { name: "Selection research market" }), "72h")
    expect(screen.getByRole("combobox", { name: "Event coverage market" })).toHaveValue("72h")
    expect(screen.getByRole("button", { name: "72-hole matchups" })).toHaveAttribute("aria-pressed", "true")
    expect(readJson).toHaveBeenCalledTimes(1)
  })

  it("explains withheld round returns and preserves secondary outcome counts in explicit details", async () => {
    const user = userEvent.setup()
    renderPage()
    const market = await screen.findByRole("button", { name: "18-hole matchups" })
    const row = within(market.closest("tr")!)
    expect(row.getByText("20 missing round IDs; those returns withheld.")).toBeInTheDocument()
    const disclosure = row.getByText("Outcome & evidence details")
    expect(disclosure.closest("details")).not.toHaveAttribute("open")
    await user.click(disclosure)
    expect(disclosure.closest("details")).toHaveAttribute("open")
    expect(row.getByText("Qualified zero returns")).toBeInTheDocument()
    expect(row.getByText("Stored voids")).toBeInTheDocument()
    expect(row.getByText("20 incomplete · 0 conflicting")).toBeInTheDocument()
    expect(screen.getByText(/Incomplete and conflict counts can overlap/)).toBeInTheDocument()
  })

  it("distinguishes archived-card-only events and scopes card source counts by market", async () => {
    const report = structuredClone(fixture)
    report.events[2].cards = 3
    report.events[2].markets = [{ key: "72h", records: 0, cards: 2 }, { key: "18h", records: 0, cards: 1 }]
    readJson.mockResolvedValue(report)
    const user = userEvent.setup()
    renderPage()
    const coverage = await screen.findByRole("group", { name: "All markets event coverage" })
    const cardOnly = within(coverage).getByRole("button", { name: /Missing Open.*0 recovered records, Archived card only/ })
    expect(cardOnly).toHaveClass("has-cards")
    await user.click(cardOnly)
    let selected = within(screen.getByRole("heading", { name: "Missing Open" }).closest(".md-season-event") as HTMLElement)
    expect(selected.getByText("Archived card rows").nextElementSibling).toHaveTextContent("3")
    expect(selected.getByText("All market records").nextElementSibling).toHaveTextContent("0")
    await user.click(screen.getByRole("button", { name: "18-hole matchups" }))
    selected = within(screen.getByRole("heading", { name: "Missing Open" }).closest(".md-season-event") as HTMLElement)
    expect(selected.getByText("This market’s archived card rows").nextElementSibling).toHaveTextContent("1")
    expect(selected.getByText("18-hole matchups records").nextElementSibling).toHaveTextContent("0")
    expect(selected.getByText(/Archived cards are source evidence, not settled records/)).toBeInTheDocument()
  })

  it("filters coverage by market while retaining missing and future calendar events", async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(await screen.findByRole("button", { name: "18-hole matchups" }))
    const coverage = screen.getByRole("group", { name: "18-hole matchups event coverage" })
    expect(within(coverage).getAllByRole("button")).toHaveLength(4)
    expect(within(coverage).getByRole("button", { name: /Sony Open.*0 recovered records, No reconciled picks/ })).toBeInTheDocument()
    expect(within(coverage).getByRole("button", { name: /Missing Open.*No reconciled picks/ })).toBeInTheDocument()
    expect(within(coverage).getByRole("button", { name: /Future Open.*Upcoming/ })).toBeInTheDocument()
    await user.click(within(coverage).getByRole("button", { name: /The American Express.*20 recovered records/ }))
    expect(screen.getByRole("heading", { name: "The American Express" })).toBeInTheDocument()
    expect(screen.getByText("18-hole matchups records")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "18-hole matchups" }))
    expect(screen.getByRole("group", { name: "All markets event coverage" })).toBeInTheDocument()
    expect(readJson).toHaveBeenCalledTimes(1)
  })

  it("supports keyboard event inspection without adding a tab stop for every calendar mark", async () => {
    const user = userEvent.setup()
    renderPage()
    const coverage = await screen.findByRole("group", { name: "All markets event coverage" })
    const marks = within(coverage).getAllByRole("button")
    expect(marks.filter(mark => mark.tabIndex === 0)).toHaveLength(1)
    marks[0].focus()
    await user.keyboard("{ArrowRight}")
    expect(marks[1]).toHaveFocus()
    expect(marks[1]).toHaveAttribute("aria-pressed", "true")
    expect(screen.getByRole("heading", { name: "The American Express" })).toBeInTheDocument()
    await user.keyboard("{End}")
    expect(marks[3]).toHaveFocus()
    expect(screen.getByRole("heading", { name: "Future Open" })).toBeInTheDocument()
  })

  it("rejects an unexpected report and retries without presenting invented empty totals", async () => {
    readJson.mockResolvedValueOnce({ state: "available", markets: [] })
    const user = userEvent.setup()
    renderPage()
    expect(await screen.findByRole("alert")).toHaveTextContent("The season report is unavailable.")
    expect(screen.queryByText("0 events")).not.toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Try again" }))
    expect(await screen.findByText("+4.50u")).toBeInTheDocument()
    expect(readJson).toHaveBeenCalledTimes(2)
  })

  it("cancels current-store reads when switching to the season report", async () => {
    let storeSignal: AbortSignal | undefined
    readJson.mockImplementation((path: string, signal: AbortSignal) => {
      if (path === SEASON_REPORT_PATH) return Promise.resolve(fixture)
      storeSignal = signal
      return new Promise((_resolve, reject) => signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true }))
    })
    const user = userEvent.setup()
    renderPage("/evidence?view=store")
    expect(await screen.findByText("Reading the results…")).toBeInTheDocument()
    await user.click(screen.getByRole("link", { name: "Season record" }))
    expect(await screen.findByText("Stored paper records.")).toBeInTheDocument()
    await waitFor(() => expect(storeSignal?.aborted).toBe(true))
    expect(getBoard).not.toHaveBeenCalled()
  })

  it("cancels a pending season read when leaving Results", async () => {
    let reportSignal: AbortSignal | undefined
    readJson.mockImplementation((_path: string, signal: AbortSignal) => {
      reportSignal = signal
      return new Promise((_resolve, reject) => signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true }))
    })
    const user = userEvent.setup()
    renderPage("/evidence")
    expect(await screen.findByText("Reading the season record…")).toBeInTheDocument()
    await user.click(screen.getByRole("link", { name: /My card/ }))
    await waitFor(() => expect(reportSignal?.aborted).toBe(true))
    expect(screen.getByRole("heading", { name: "Your card." })).toBeInTheDocument()
    expect(getBoard).not.toHaveBeenCalled()
  })
})
