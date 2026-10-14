import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import type { OperatorBoard } from "@/features/operator-data/operator-api"
import { CARD_KEY } from "./market-rows"
import { MatchupDesk } from "./matchup-desk"

const { getBoard } = vi.hoisted(() => ({ getBoard: vi.fn() }))
vi.mock("@/features/operator-data/operator-api", async importOriginal => ({ ...await importOriginal<typeof import("@/features/operator-data/operator-api")>(), getDeskBoard: getBoard }))
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
  it("opens My card without any live API requests", async () => {
    renderDesk("/card")
    expect(screen.getByRole("heading", { name: "Your card." })).toBeInTheDocument()
    await waitFor(() => expect(screen.getByRole("heading", { name: "A considered card starts here." })).toBeInTheDocument())
    expect(getBoard).not.toHaveBeenCalled()
    expect(fetchMock).not.toHaveBeenCalled()
    expect(screen.queryByText("Loading event…")).not.toBeInTheDocument()
  })

  it("cancels an obsolete board request when opening My card", async () => {
    let requestSignal: AbortSignal | undefined
    getBoard.mockImplementation((_options, signal: AbortSignal) => {
      requestSignal = signal
      return new Promise((_resolve, reject) => signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true }))
    })
    const user = userEvent.setup()
    renderDesk()
    await user.click(screen.getByRole("link", { name: /My card/ }))
    await waitFor(() => expect(requestSignal?.aborted).toBe(true))
    expect(screen.getByRole("heading", { name: "Your card." })).toBeInTheDocument()
  })

  it("loads Results without an unrelated board request", async () => {
    renderDesk("/evidence")
    expect(await screen.findByText("No settled market evidence yet.")).toBeInTheDocument()
    expect(getBoard).not.toHaveBeenCalled()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock.mock.calls[0][1].signal).toBeInstanceOf(AbortSignal)
  })

  it("keeps filters and event context when visiting My card and returning", async () => {
    const user = userEvent.setup()
    renderDesk("/?mode=upcoming&market=72h&q=Scottie&book=fanduel&ev=2&sort=player")
    await screen.findByRole("button", { name: "Save Scottie Scheffler to card" })
    await user.click(screen.getByRole("link", { name: /My card/ }))
    await user.click(screen.getByRole("link", { name: "Markets" }))
    expect(screen.getByRole("textbox", { name: "Find a player or matchup" })).toHaveValue("Scottie")
    expect(screen.getByRole("combobox", { name: "Sportsbook" })).toHaveValue("fanduel")
    expect(screen.getByRole("combobox", { name: "Minimum model EV" })).toHaveValue("2")
    expect(getBoard).toHaveBeenCalledTimes(1)
  })

  it("withholds cached quotes while rechecking an aged board after visiting My card", async () => {
    const user = userEvent.setup()
    renderDesk()
    await screen.findByRole("button", { name: "Save Scottie Scheffler to card" })
    await user.click(screen.getByRole("link", { name: /My card/ }))
    await clients.at(-1)!.invalidateQueries({ queryKey: ["matchup-desk"] })
    getBoard.mockImplementation(() => new Promise(() => {}))
    await user.click(screen.getByRole("link", { name: "Markets" }))
    const save = screen.getByRole("button", { name: "Save Scottie Scheffler to card" })
    expect(save).toBeDisabled()
    expect(screen.getByText("Checking latest quotes…")).toBeInTheDocument()
    await user.click(save)
    expect(localStorage.getItem(CARD_KEY)).toBeNull()
  })

  it("creates a share link from selected original picks without changing the personal card", async () => {
    const second = { ...quote, pick: "Ludvig Åberg", pick_key: "aberg", odds: "-105" }
    getBoard.mockResolvedValue(board({ picks: { matchups: [{ ...quote }, second], value_bets: [] } }))
    const user = userEvent.setup()
    renderDesk()
    await user.click(await screen.findByRole("button", { name: "Save Scottie Scheffler to card" }))
    await user.click(screen.getByRole("button", { name: "Save Ludvig Åberg to card" }))
    await user.click(screen.getByRole("link", { name: /My card/ }))
    const original = localStorage.getItem(CARD_KEY)
    await user.click(screen.getByRole("button", { name: "Share picks" }))
    await user.click(screen.getByRole("checkbox", { name: /Ludvig Åberg/ }))
    await user.click(screen.getByRole("button", { name: "Create share link" }))
    const link = await screen.findByRole("textbox", { name: "Share link" })
    const url = new URL((link as HTMLInputElement).value)
    expect(url.pathname).toBe("/shared-card")
    const { decodeSharedCard } = await import("./shared-card")
    const shared = await decodeSharedCard(new URLSearchParams(url.hash.slice(1)).get("card")!)
    expect(shared.picks).toEqual([JSON.parse(original!)[0]])
    expect(localStorage.getItem(CARD_KEY)).toBe(original)
    expect(screen.getByRole("link", { name: /Preview shared card/ })).toHaveAttribute("href", url.toString())
  })

  it("clears manual-copy text when a pick is excluded from sharing", async () => {
    getBoard.mockResolvedValue(board({ picks: { matchups: [{ ...quote }, { ...quote, pick: "Ludvig Åberg", pick_key: "aberg" }], value_bets: [] } }))
    const user = userEvent.setup()
    renderDesk()
    await user.click(await screen.findByRole("button", { name: "Save Scottie Scheffler to card" }))
    await user.click(screen.getByRole("button", { name: "Save Ludvig Åberg to card" }))
    await user.click(screen.getByRole("link", { name: /My card/ }))
    await user.click(screen.getByRole("button", { name: "Share picks" }))
    vi.spyOn(navigator.clipboard, "writeText").mockRejectedValue(new Error("Clipboard denied"))
    await user.click(screen.getByRole("button", { name: "Copy picks" }))
    expect((await screen.findByRole("textbox", { name: "Picks to copy" }) as HTMLTextAreaElement).value).toContain("Ludvig Åberg")
    await user.click(screen.getByRole("checkbox", { name: /Ludvig Åberg/ }))
    expect(screen.queryByRole("textbox", { name: "Picks to copy" })).not.toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Copy picks" }))
    const manual = await screen.findByRole("textbox", { name: "Picks to copy" })
    expect((manual as HTMLTextAreaElement).value).toContain("Scottie Scheffler")
    expect((manual as HTMLTextAreaElement).value).not.toContain("Ludvig Åberg")
  })

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
