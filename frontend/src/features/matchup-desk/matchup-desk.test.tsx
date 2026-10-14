import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import type { OperatorBoard } from "@/features/operator-data/operator-api"
import { CARD_KEY } from "./market-rows"
import { MatchupDesk } from "./matchup-desk"

const { getBoard } = vi.hoisted(() => ({ getBoard: vi.fn() }))
vi.mock("@/features/operator-data/operator-api", () => ({ getDeskBoard: getBoard }))
vi.mock("@/components/theme-toggle", () => ({ ThemeToggle: () => null }))

const quote = {
  pick: "Scottie Scheffler", pick_key: "scottie", opponent: "Rory McIlroy", opponent_key: "rory",
  market_type: "tournament_matchups", book: "fanduel", odds: "+110", model_win_prob: 0.563,
  ev: 0.028, reason: "Original model explanation", line_seen_at: "2026-10-13T12:00:00Z",
}
function board(overrides: Partial<OperatorBoard> = {}): OperatorBoard {
  return {
    schema_version: "operator-read-model/v1", track: "champion", mode: "upcoming", state: "fresh",
    reason: { code: "ready", message: "Ready" }, event: { event_id: "event-1", event_name: "Test Open" },
    source: { generated_at: "2026-10-13T12:00:00Z", age_seconds: 5 }, eligibility: { verified: true },
    rankings: [], leaderboard: [], picks: { matchups: [{ ...quote }], value_bets: [] }, ...overrides,
  }
}
const clients: QueryClient[] = []
function renderDesk(route = "/") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  clients.push(client)
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[route]}><MatchupDesk /></MemoryRouter></QueryClientProvider>)
}
let fetchMock: ReturnType<typeof vi.fn>
beforeEach(() => {
  localStorage.clear()
  getBoard.mockReset().mockResolvedValue(board())
  fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ state: "available", coverage: { event_count: 2 }, markets: [] }) })
  vi.stubGlobal("fetch", fetchMock)
})
afterEach(() => {
  cleanup()
  clients.splice(0).forEach(client => client.clear())
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe("matchup desk user flow", () => {
  it("saves an original quote, restores it after a remount, exports it, and removes it without placing bets", async () => {
    const user = userEvent.setup()
    const first = renderDesk()
    await user.click(await screen.findByRole("button", { name: "Save Scottie Scheffler to card" }))
    expect(screen.getByRole("button", { name: "Scottie Scheffler saved to card" })).toBeInTheDocument()
    await user.click(screen.getByRole("link", { name: /My card/ }))
    expect(screen.getByRole("heading", { name: "Your card." })).toBeInTheDocument()
    const stored = JSON.parse(localStorage.getItem(CARD_KEY) || "[]")
    expect(stored).toHaveLength(1)
    expect(stored[0]).toMatchObject({ eventId: "event-1", odds: "+110", probability: 0.563, ev: 0.028, reason: "Original model explanation" })
    first.unmount()

    renderDesk("/card")
    expect(screen.getByRole("heading", { name: "Scottie Scheffler" })).toBeInTheDocument()
    expect(screen.getByText("56.3%")).toBeInTheDocument()
    expect(screen.getByText("+2.8%")).toBeInTheDocument()
    expect(screen.getByText(/no bets have been placed/)).toBeInTheDocument()
    const createUrl = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:card-export")
    const revokeUrl = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {})
    const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {})
    await user.click(screen.getByRole("button", { name: "Export card" }))
    expect(anchorClick).toHaveBeenCalledOnce()
    expect(revokeUrl).toHaveBeenCalledWith("blob:card-export")
    const csv = await (createUrl.mock.calls[0][0] as Blob).text()
    expect(csv).toContain("event,market,round,player,opponent,book,odds,model_probability,model_ev")
    expect(csv).toContain('"Scottie Scheffler","Rory McIlroy","fanduel","+110","0.563","0.028"')
    expect(fetchMock.mock.calls.every(([, init]) => !init?.method || init.method === "GET")).toBe(true)

    await user.click(screen.getByRole("button", { name: "Remove Scottie Scheffler from card" }))
    expect(screen.getByRole("heading", { name: "A considered card starts here." })).toBeInTheDocument()
    expect(JSON.parse(localStorage.getItem(CARD_KEY) || "null")).toEqual([])
  })

  it("keeps an unknown-duration matchup in other markets and filters decimal EV correctly", async () => {
    getBoard.mockResolvedValue(board({ picks: { matchups: [{ ...quote, market_type: "matchup" }], value_bets: [] } }))
    const user = userEvent.setup()
    renderDesk()
    const durations = screen.getByRole("group", { name: "Market duration" })
    await waitFor(() => expect(within(durations).getByRole("button", { name: /Other markets\s*1/ })).toBeInTheDocument())
    expect(within(durations).getByRole("button", { name: /72 holes\s*0/ })).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Save Scottie Scheffler to card" })).not.toBeInTheDocument()
    await user.click(within(durations).getByRole("button", { name: /Other markets/ }))
    expect(await screen.findByText("+2.8%")).toBeInTheDocument()
    await user.selectOptions(screen.getByRole("combobox", { name: "Minimum model EV" }), "3")
    expect(screen.getByRole("heading", { name: "No matchups fit these filters." })).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Clear filters" }))
    expect(screen.getByText("+2.8%")).toBeInTheDocument()
  })

  it.each([0.49, undefined])("shows only supplied bookmaker probability in matchup details (%s)", async implied => {
    getBoard.mockResolvedValue(board({ picks: { matchups: [{ ...quote, implied_prob: implied }], value_bets: [] } }))
    const user = userEvent.setup()
    renderDesk()
    await user.click(await screen.findByRole("button", { name: /Scottie Scheffler vs Rory McIlroy/ }))
    expect(screen.getByText("Original model explanation")).toBeInTheDocument()
    if (implied === undefined) {
      expect(screen.queryByText("Book break-even")).not.toBeInTheDocument()
    } else {
      expect(screen.getByText("Book break-even")).toBeInTheDocument()
      expect(screen.getByText("49.0%")).toBeInTheDocument()
    }
    expect(screen.queryByText("43.7%")).not.toBeInTheDocument()
  })

  it.each(["stale", "inplay", "research"])("does not save %s quotes", async kind => {
    getBoard.mockResolvedValue(board({
      state: kind === "stale" ? "stale" : "fresh",
      mode: kind === "inplay" ? "live" : "upcoming",
      picks: { matchups: [{ ...quote, ...(kind === "research" ? { shadow_only: true } : {}) }], value_bets: [] },
    }))
    const user = userEvent.setup()
    renderDesk(kind === "inplay" ? "/?mode=live" : "/")
    const save = await screen.findByRole("button", { name: "Save Scottie Scheffler to card" })
    expect(save).toBeDisabled()
    await user.click(save)
    expect(localStorage.getItem(CARD_KEY)).toBeNull()
  })

  it("withholds an unavailable board even when its payload contains a quote", async () => {
    getBoard.mockResolvedValue(board({ state: "unavailable" }))
    renderDesk()
    expect(await screen.findByRole("heading", { name: "This event needs verification." })).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Save Scottie Scheffler to card" })).not.toBeInTheDocument()
  })

  it("opens an empty card safely after malformed browser storage", () => {
    localStorage.setItem(CARD_KEY, "not-json")
    renderDesk("/card")
    expect(screen.getByRole("heading", { name: "A considered card starts here." })).toBeInTheDocument()
  })
})
