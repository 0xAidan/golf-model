import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import type { OperatorBoard } from "@/features/operator-data/operator-api"
import { boardRows, CARD_KEY, formatEdge, formatProbability, marketFamily, readSavedCard, readVisibleMarkets, MARKET_FAMILIES, VISIBLE_MARKETS_KEY } from "./market-rows"

const quote = {
  pick: "Scottie Scheffler", pick_key: "scottie", opponent: "Rory McIlroy", opponent_key: "rory",
  market_type: "tournament_matchups", book: "fanduel", odds: "+110",
  model_win_prob: 0.563, ev: 0.028, reason: "Original model explanation",
}
function board(overrides: Partial<OperatorBoard> = {}): OperatorBoard {
  return {
    schema_version: "operator-read-model/v1", track: "champion", mode: "upcoming", state: "fresh",
    reason: { code: "ready", message: "Ready" }, event: { event_id: "event-1", event_name: "Test Open" },
    source: { generated_at: "2026-10-13T12:00:00Z", age_seconds: 5 }, eligibility: { verified: true },
    rankings: [], leaderboard: [], picks: { matchups: [{ ...quote }], value_bets: [] }, ...overrides,
  }
}
const withQuote = (overrides: Record<string, unknown>) => board({
  picks: { matchups: [{ ...quote, ...overrides }], value_bets: [] },
})

beforeEach(() => localStorage.clear())
afterEach(() => vi.restoreAllMocks())

describe("market identity and original values", () => {
  it.each(["matchup", "matchups", "head_to_head", "h2h", "", undefined])(
    "keeps duration unspecified for %s instead of assuming 72 holes", (value) => {
      expect(marketFamily(value)).toBe("other")
    },
  )
  it.each([
    ["tournament_matchups", "72h"], ["72-hole", "72h"],
    ["round_matchups", "18h"], ["18 holes", "18h"],
    ["three_ball", "group"], ["3_balls", "group"], ["group", "group"],
    ["win", "outright"], ["outright", "outright"], ["top_5", "top5"],
    ["top10", "top10"], ["top-20", "top20"], ["first_round_leader", "frl"],
    ["make_cut", "make_cut"], ["miss_cut", "miss_cut"],
  ])("recognizes explicit market duration %s", (input, expected) => {
    expect(marketFamily(input)).toBe(expected)
  })
  it("preserves decimal EV and supplied probability while formatting percentages", () => {
    const original = board()
    const snapshot = structuredClone(original)
    const [row] = boardRows(original)
    expect(row.ev).toBe(0.028)
    expect(row.probability).toBe(0.563)
    expect(formatEdge(row.ev)).toBe("+2.8%")
    expect(formatProbability(row.probability)).toBe("56.3%")
    expect(formatEdge(null)).toBe("—")
    expect(formatEdge(-0.041)).toBe("-4.1%")
    expect(original).toEqual(snapshot)
  })
  it("keeps event, mode, duration, round, group, side, book, and price identities distinct", () => {
    const boards = [
      board(), board({ event: { event_id: "event-2" } }), board({ mode: "live" }),
      withQuote({ market_type: "round_matchups", round_num: 1 }),
      withQuote({ market_type: "round_matchups", round_num: 2 }),
      withQuote({ group_id: "group-2" }), withQuote({ pick_key: "different-player" }),
      withQuote({ opponent_key: "different-opponent" }), withQuote({ book: "draftkings" }),
      withQuote({ odds: "+115" }),
    ]
    expect(new Set(boards.flatMap(boardRows).map(row => row.id)).size).toBe(boards.length)
  })
  it("deduplicates only identical quotes while preserving two books for the same pair", () => {
    const rows = boardRows(board({ picks: { matchups: [quote, { ...quote }, { ...quote, book: "draftkings" }], value_bets: [] } }))
    expect(rows).toHaveLength(2)
    expect(rows.map(row => row.book)).toEqual(["fanduel", "draftkings"])
  })
  it("keeps separate round_number and group market_id quotes", () => {
    const matchups = [
      { ...quote, market_type: "round_matchups", round_number: 1 },
      { ...quote, market_type: "round_matchups", round_number: 2 },
      { ...quote, market_type: "group", group_id: "same-group", market_id: "market-1" },
      { ...quote, market_type: "group", group_id: "same-group", market_id: "market-2" },
    ]
    const rows = boardRows(board({ picks: { matchups, value_bets: [] } }))
    expect(rows).toHaveLength(4)
    expect(rows.slice(0, 2).map(row => row.round)).toEqual(["1", "2"])
    expect(rows.every(row => row.eligible)).toBe(true)
  })
  it("retains existing quote keys when no new market identity is supplied", () => {
    expect(boardRows(board())[0].id).toBe(JSON.stringify([
      "event-1", "upcoming", "tournament_matchups", "", "", "scottie", "rory", "fanduel", "+110",
    ]))
  })
  it.each([{ implied_prob: 0.49 }, { market_prob: 0.49 }])("preserves supplied bookmaker probability %j", fields => {
    const [row] = boardRows(withQuote(fields))
    expect(row.impliedProbability).toBe(0.49)
    expect(row.probability).toBe(0.563)
    expect(row.ev).toBe(0.028)
  })
  it.each([{}, { implied_prob: 1.1 }, { implied_prob: "not-a-number" }])("leaves missing or invalid bookmaker probability empty %j", fields => {
    expect(boardRows(withQuote(fields))[0].impliedProbability).toBeNull()
  })
})

describe("card eligibility", () => {
  it("allows a complete fresh upcoming quote", () => expect(boardRows(board())[0].eligible).toBe(true))
  it("keeps stale quotes visible but disables saving", () => expect(boardRows(board({ state: "stale" }))[0].eligible).toBe(false))
  it.each(["unavailable", "error"] as const)("withholds %s board rows", state => {
    expect(boardRows(board({ state }))).toEqual([])
  })
  it.each([{ verified: false }, { verified: true, field_event_id: "wrong-event" }])("withholds a failed or mismatched field %j", eligibility => {
    expect(boardRows(board({ eligibility }))).toEqual([])
  })
  it.each(["DataGolf", "Data Golf", "dg", "synthetic"])("keeps %s model prices in research", book => {
    expect(boardRows(withQuote({ book }))[0].eligible).toBe(false)
  })
  it.each(["live", "past"] as const)("does not allow %s context onto the card", mode => {
    expect(boardRows(board({ mode }))[0].eligible).toBe(false)
  })
  it.each([
    { market_provenance: "shadow" }, { market_provenance: "research" },
    { market_provenance: "simulated" }, { shadow_only: true }, { research_only: true },
    { live_bettable: false }, { market_type: "inplay_round_matchups" }, { market_type: "live_round_matchups" },
  ])("does not save research, withheld, or in-play quote %j", fields => {
    expect(boardRows(withQuote(fields))[0].eligible).toBe(false)
  })
  it.each([undefined, 0, 5, 1.5, "unknown"])("keeps an 18-hole quote with invalid round %s as research", round => {
    expect(boardRows(withQuote({ market_type: "round_matchups", round }))[0].eligible).toBe(false)
  })
  it.each([
    { round_num: 1 }, { round_number: 2 }, { round: "3" },
    { round: "R4" }, { market_type: "round_2_matchups" },
  ])("accepts explicit valid round identity %j", fields => {
    const [row] = boardRows(withQuote({ market_type: "round_matchups", ...fields }))
    expect(row.eligible).toBe(true)
    expect(row.round).toMatch(/^[1-4]$/)
  })
  it.each([{}, { group_id: " " }, { opponent_key: "one-opponent" }])("withholds group quotes without a complete group/market identifier %j", fields => {
    expect(boardRows(withQuote({ market_type: "group", ...fields }))[0].eligible).toBe(false)
  })
  it.each([{ group_id: "group-1" }, { market_id: "market-1" }])("accepts an explicitly identified group quote %j", fields => {
    expect(boardRows(withQuote({ market_type: "group", ...fields }))[0].eligible).toBe(true)
  })
  it.each([true, false, [], [0.56], {}, " "].map(probability => ({ probability })))("does not coerce malformed probability $probability into an eligible forecast", ({ probability }) => {
    const [row] = boardRows(withQuote({ model_win_prob: probability }))
    expect(row.probability).toBeNull()
    expect(row.eligible).toBe(false)
  })
})

describe("visible market preferences", () => {
  it("restores an explicit all-off preference without changing saved selections", () => {
    localStorage.setItem(VISIBLE_MARKETS_KEY, "[]")
    localStorage.setItem(CARD_KEY, "preserved")
    expect(readVisibleMarkets()).toEqual([])
    expect(localStorage.getItem(CARD_KEY)).toBe("preserved")
  })
  it("falls back safely on malformed or blocked preference storage", () => {
    localStorage.setItem(VISIBLE_MARKETS_KEY, '["not-a-market"]')
    expect(readVisibleMarkets()).toEqual(MARKET_FAMILIES)
    vi.spyOn(localStorage, "getItem").mockImplementation(() => { throw new Error("Blocked") })
    expect(readVisibleMarkets()).toEqual(MARKET_FAMILIES)
  })
})

describe("saved-card recovery", () => {
  it.each(["broken-json", "null", "{}", '[null, 5, "bad", {}]'])("safely ignores corrupt storage %s", raw => {
    localStorage.setItem(CARD_KEY, raw)
    expect(readSavedCard()).toEqual([])
  })
  it("retains valid complete saved quotes but rejects partial objects that would crash the card", () => {
    const saved = { ...boardRows(board())[0], savedAt: "2026-10-13T12:05:00Z" }
    const partial = { id: "broken", player: "Broken Player", eventId: "event-1", savedAt: "2026-10-13T12:05:00Z" }
    localStorage.setItem(CARD_KEY, JSON.stringify([saved, partial]))
    expect(readSavedCard()).toEqual([saved])
  })
  it("does not throw when local storage cannot be read", () => {
    vi.spyOn(localStorage, "getItem").mockImplementation(() => { throw new Error("Storage blocked") })
    expect(readSavedCard()).toEqual([])
  })
})
