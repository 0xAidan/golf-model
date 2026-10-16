import { cleanup, render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { boardRows, CARD_KEY, type SavedPick } from "./market-rows"
import { createSharedCard, encodeSharedCard } from "./shared-card"
import SharedCardPage from "./shared-card-page"

vi.mock("@/components/theme-toggle", () => ({ ThemeToggle: () => null }))
const pick: SavedPick = { ...boardRows({ schema_version: "operator-read-model/v1", track: "champion", mode: "upcoming", state: "fresh", reason: { code: "ready", message: "Ready" }, source: { generated_at: "2026-10-13T12:00:00Z" }, event: { event_id: "event-1", event_name: "Test Open" }, eligibility: { verified: true }, rankings: [], leaderboard: [], picks: { matchups: [{ pick: "Ludvig Åberg", player_key: "aberg", opponent: "Rory McIlroy", market_type: "tournament_matchups", book: "fanduel", odds: "+110", model_win_prob: .563, ev: .028, reason: "Original explanation" }], value_bets: [] } })[0], savedAt: "2026-10-13T12:05:00Z" }
beforeEach(() => { localStorage.setItem(CARD_KEY, "existing personal card"); vi.stubGlobal("fetch", vi.fn()) })
afterEach(() => { cleanup(); vi.unstubAllGlobals(); localStorage.clear() })

describe("shared picks reader", () => {
  it("opens an exact snapshot with no API dependency or personal-card changes", async () => {
    const token = await encodeSharedCard(createSharedCard([pick], "2026-10-13T12:10:00Z"))
    render(<MemoryRouter initialEntries={[`/shared-card#card=${token}`]}><SharedCardPage /></MemoryRouter>)
    expect(await screen.findByRole("heading", { name: "Ludvig Åberg" })).toBeInTheDocument()
    expect(screen.getByText("+110")).toBeInTheDocument()
    expect(screen.getByText("56.3%")).toBeInTheDocument()
    expect(screen.getByText(/prices may have moved/)).toBeInTheDocument()
    await userEvent.setup().click(screen.getByRole("link", { name: "Skip to picks" }))
    expect(screen.getByRole("heading", { name: "Ludvig Åberg" })).toBeInTheDocument()
    expect(document.activeElement).toBe(screen.getByRole("main"))
    expect(screen.queryByRole("button", { name: /Remove/ })).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /Save .* card/ })).not.toBeInTheDocument()
    expect(fetch).not.toHaveBeenCalled()
    expect(localStorage.getItem(CARD_KEY)).toBe("existing personal card")
  })
  it.each(["", "#card=bad", "#card=bad&card=duplicate", "#card=bad&extra=1"])("handles an invalid share link safely: %s", async hash => {
    render(<MemoryRouter initialEntries={[`/shared-card${hash}`]}><SharedCardPage /></MemoryRouter>)
    expect(await screen.findByRole("heading", { name: "This card couldn’t open." })).toBeInTheDocument()
    expect(fetch).not.toHaveBeenCalled()
    expect(localStorage.getItem(CARD_KEY)).toBe("existing personal card")
  })
})
