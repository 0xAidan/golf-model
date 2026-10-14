/// <reference types="node" />

import { CompressionStream as NativeCompressionStream, DecompressionStream as NativeDecompressionStream, ReadableStream as NativeReadableStream } from "node:stream/web"
import { gzipSync } from "node:zlib"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import type { SavedPick } from "./market-rows"
import { createSharedCard, decodeSharedCard, encodeSharedCard, formatSharedPicksText, MAX_SHARED_JSON_BYTES, MAX_SHARED_PICKS, MAX_SHARED_TOKEN_LENGTH } from "./shared-card"

const savedAt = "2026-10-13T12:05:00.123Z"
const sharedAt = "2026-10-13T12:06:00Z"
function pick(overrides: Partial<SavedPick> = {}, group = "", marketId?: string): SavedPick {
  const row: SavedPick = {
    id: "", eventId: "event-1", eventName: "L’Open — Montréal ⛳", mode: "upcoming", market: "72h",
    marketType: "tournament_matchups", round: "", player: "José María", playerKey: "jose_maria", opponent: "Ludvig Åberg",
    book: "Book A", odds: "+110.00", probability: 0.563214, impliedProbability: 0.47619, ev: 0.028012,
    reason: "Original explanation — 保持原样.\nSecond line.", lineAt: "2026-10-13T07:59:20-04:00",
    snapshotAt: "2026-10-13T12:00:00.123456Z", eligible: true, savedAt, ...overrides,
  }
  const identity = [row.eventId, row.mode, row.marketType, row.round, group, row.playerKey, "ludvig_aberg", row.book, row.odds]
  if (marketId) identity.push(marketId)
  row.id = overrides.id ?? JSON.stringify(identity)
  return row
}
const token = (value: unknown) => `json1.${Buffer.from(JSON.stringify(value)).toString("base64url")}`
const compressedToken = (bytes: string | Uint8Array) => `gz1.${gzipSync(bytes).toString("base64url")}`

beforeEach(() => {
  vi.stubGlobal("CompressionStream", NativeCompressionStream)
  vi.stubGlobal("DecompressionStream", NativeDecompressionStream)
  vi.stubGlobal("ReadableStream", NativeReadableStream)
})
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })

describe("shared snapshot preservation", () => {
  it("round-trips every original field, unicode, prices and timestamp precision through gzip", async () => {
    const input = [pick(), pick({ market: "18h", marketType: "round_matchups", round: "2", odds: "-105" })]
    const before = structuredClone(input)
    const card = createSharedCard(input, sharedAt)
    const encoded = await encodeSharedCard(card)
    expect(encoded.startsWith("gz1.")).toBe(true)
    expect(encoded).toMatch(/^[\w.-]+$/)
    expect(await decodeSharedCard(encoded)).toEqual({ version: 1, createdAt: sharedAt, picks: before })
    expect(input).toEqual(before)
    card.picks[0].reason = "Changed copy"
    expect(input).toEqual(before)
  })
  it("retains optional probability absence and original naive quote timestamps", async () => {
    const original = pick({ lineAt: "2026-10-13 12:00:00.123456", snapshotAt: null })
    delete original.impliedProbability
    const card = await decodeSharedCard(await encodeSharedCard(createSharedCard([original], sharedAt)))
    expect(card.picks[0]).toEqual(original)
    expect(Object.hasOwn(card.picks[0], "impliedProbability")).toBe(false)
  })
  it("preserves group identity carried by either the group key or market key", async () => {
    const input = [pick({ market: "group", marketType: "three_ball" }, "group-9"), pick({ market: "group", marketType: "three_ball" }, "", "contract-10")]
    expect((await decodeSharedCard(await encodeSharedCard(createSharedCard(input, sharedAt)))).picks).toEqual(input)
  })
  it("falls back to an explicitly versioned uncompressed encoding", async () => {
    vi.stubGlobal("CompressionStream", undefined)
    vi.stubGlobal("DecompressionStream", undefined)
    const card = createSharedCard([pick()], sharedAt)
    const encoded = await encodeSharedCard(card)
    expect(encoded.startsWith("json1.")).toBe(true)
    expect(await decodeSharedCard(encoded)).toEqual(card)
  })
  it("does not read or write storage or use the network", async () => {
    const get = vi.spyOn(localStorage, "getItem"), set = vi.spyOn(localStorage, "setItem")
    const fetch = vi.fn(() => { throw new Error("Network forbidden") })
    vi.stubGlobal("fetch", fetch)
    const card = createSharedCard([pick()], sharedAt)
    await decodeSharedCard(await encodeSharedCard(card))
    formatSharedPicksText(card)
    expect(get).not.toHaveBeenCalled(); expect(set).not.toHaveBeenCalled(); expect(fetch).not.toHaveBeenCalled()
  })
  it("formats a concise recipient-ready message with original prices, times and full reason", () => {
    const original = pick()
    const text = formatSharedPicksText(createSharedCard([original], sharedAt))
    expect(text).toBe([
      "Golf shared card", `Shared: ${sharedAt}`, "Saved prices are unverified and not live; availability may have changed.",
      "", "1. L’Open — Montréal ⛳", "72 holes", "José María vs Ludvig Åberg", "Book A · +110.00",
      "Model probability: 56.32% · EV: +2.8%", `Quote time: ${original.lineAt}`, `Snapshot time: ${original.snapshotAt}`,
      `Reason: ${original.reason}`,
    ].join("\n"))
    for (const value of [original.eventId, original.id, original.marketType, "decimal", "Book probability:", "Saved:"]) expect(text).not.toContain(value)
  })
  it("shows round and group contract identity without raw quote JSON", () => {
    const round = pick({ market: "18h", marketType: "round_matchups", round: "3", odds: "-105.50", ev: -0.04 })
    const group = pick({ market: "group", marketType: "three_ball" }, "group-9", "market-10")
    const text = formatSharedPicksText(createSharedCard([round, group], sharedAt))
    expect(text).toContain("18 holes · Round 3")
    expect(text).toContain("Book A · -105.50")
    expect(text).toContain("EV: -4%")
    expect(text).toContain("Group · Contract market-10")
    expect(text).not.toContain(round.id)
    expect(text).not.toContain(group.id)
    const groupOnly = pick({ market: "group", marketType: "three_ball" }, "group-9")
    expect(formatSharedPicksText(createSharedCard([groupOnly], sharedAt))).toContain("Group · Contract group-9")
  })
  it("honestly labels missing source times and omits an absent reason or book probability", () => {
    const original = pick({ probability: null, impliedProbability: null, ev: null, lineAt: null, snapshotAt: null, reason: "" })
    const text = formatSharedPicksText(createSharedCard([original], sharedAt))
    expect(text).toContain("Model probability: Unavailable · EV: Unavailable")
    expect(text).toContain("Quote time: Unavailable")
    expect(text).toContain("Snapshot time: Unavailable")
    expect(text).not.toContain("Reason:")
    expect(text).not.toContain("Book probability:")
  })
  it("keeps exact link data unchanged when formatting a recipient message", async () => {
    const card = createSharedCard([pick({ reason: "Original explanation. ".repeat(90) })], sharedAt)
    const before = structuredClone(card)
    const text = formatSharedPicksText(card)
    expect(text).toContain(before.picks[0].reason)
    expect(card).toEqual(before)
    expect(await decodeSharedCard(await encodeSharedCard(card))).toEqual(before)
  })
  it("accepts all 32 picks without truncating", async () => {
    const picks = Array.from({ length: MAX_SHARED_PICKS }, (_, i) => pick({ eventId: `event-${i}` }))
    expect((await decodeSharedCard(await encodeSharedCard(createSharedCard(picks, sharedAt)))).picks).toEqual(picks)
  })
})

describe("rejects a malformed card as a whole", () => {
  it.each([
    { version: 2, createdAt: sharedAt, picks: [pick()] },
    { version: 1, createdAt: sharedAt, picks: [] },
    { version: 1, createdAt: sharedAt, picks: [pick(), pick()] },
    { version: 1, createdAt: sharedAt, picks: Array.from({ length: MAX_SHARED_PICKS + 1 }, (_, i) => pick({ eventId: `e-${i}` })) },
    { version: 1, createdAt: sharedAt, picks: [pick()], verified: true },
    { version: 1, createdAt: "yesterday", picks: [pick()] },
  ])("rejects an unsupported envelope without dropping rows: %#", async card => {
    await expect(decodeSharedCard(token(card))).rejects.toThrow()
  })
  it.each([
    { eventId: "" }, { eventName: " " }, { playerKey: "" }, { book: "" }, { id: "opaque" },
    { odds: "NaN" }, { odds: "+99" }, { market: "unknown" }, { mode: "verified" },
    { probability: 1.001 }, { probability: -0.01 }, { probability: "0.5" }, { impliedProbability: 2 },
    { ev: "high" }, { eligible: "true" }, { reason: "x".repeat(2049) },
    { savedAt: "2026-02-30T12:00:00Z" }, { savedAt: "2026-10-13T12:00:00" },
    { lineAt: "2026-10-13T25:00:00Z" }, { snapshotAt: "2026-10-13T12:00:00+14:01" },
    { round: "5", market: "18h", marketType: "round_matchups" },
    { market: "group", marketType: "three_ball" }, { market: "18h", marketType: "tournament_matchups", round: "2" },
  ])("rejects invalid pick fields: %j", async overrides => {
    const bad = pick(overrides as Partial<SavedPick>)
    await expect(decodeSharedCard(token({ version: 1, createdAt: sharedAt, picks: [pick(), bad] }))).rejects.toThrow()
  })
  it("rejects contradictory embedded identity without rebuilding it", async () => {
    const original = pick()
    const changed = { ...original, odds: "+120" }
    await expect(decodeSharedCard(token({ version: 1, createdAt: sharedAt, picks: [changed] }))).rejects.toThrow("Conflicting quote identity")
    expect(changed.id).toBe(original.id)
  })
  it("rejects equivalent identities even when their JSON string spacing differs", () => {
    const first = pick()
    const same = { ...first, id: first.id.replaceAll(",", ", ") }
    expect(() => createSharedCard([first, same], sharedAt)).toThrow("Duplicate")
  })
  it("rejects nonfinite input before JSON serialization can replace it with null", () => {
    for (const bad of [pick({ probability: NaN }), pick({ ev: Infinity }), pick({ impliedProbability: -Infinity })]) {
      expect(() => createSharedCard([bad], sharedAt)).toThrow()
    }
  })
  it("rejects sparse input without silently converting a missing pick into null", () => {
    expect(() => createSharedCard(new Array<SavedPick>(1), sharedAt)).toThrow("Invalid saved pick")
  })
  it("rejects missing and unknown fields rather than discarding them", async () => {
    const missing = { ...pick() } as Partial<SavedPick>
    delete missing.eligible
    for (const bad of [missing, { ...pick(), verified: true }]) {
      await expect(decodeSharedCard(token({ version: 1, createdAt: sharedAt, picks: [bad] }))).rejects.toThrow()
    }
  })
  it("rejects duplicate object keys, invalid UTF-8 and corrupt JSON", async () => {
    const valid = JSON.stringify(createSharedCard([pick()], sharedAt))
    for (const body of [valid.replace('"version":1', '"version":1,"version":1'), "{broken", new Uint8Array([0xc3, 0x28])]) {
      await expect(decodeSharedCard(compressedToken(body))).rejects.toThrow("Malformed")
    }
  })
})

describe("resource and compression limits", () => {
  it.each(["gz2.AA", "json1.A", "json1.AA=", "json1.AB", "gz1.not-gzip", "", "https://example.com/shared-card#card=json1.AA"])("rejects malformed/versioned tokens %s", async value => {
    await expect(decodeSharedCard(value)).rejects.toThrow()
  })
  it("rejects oversized encoded input before decoding", async () => {
    await expect(decodeSharedCard(`json1.${"A".repeat(MAX_SHARED_TOKEN_LENGTH)}`)).rejects.toThrow("size limit")
  })
  it("stops a small gzip bomb at the decompressed byte limit", async () => {
    const bomb = compressedToken("A".repeat(MAX_SHARED_JSON_BYTES * 32))
    expect(bomb.length).toBeLessThan(MAX_SHARED_TOKEN_LENGTH)
    await expect(decodeSharedCard(bomb)).rejects.toThrow("data-size limit")
  })
  it("rejects a truncated gzip stream and CRC corruption", async () => {
    const gzip = gzipSync(JSON.stringify(createSharedCard([pick()], sharedAt)))
    const wrongCRC = Buffer.from(gzip); wrongCRC[wrongCRC.length - 8] ^= 0xff
    for (const bytes of [gzip.subarray(0, gzip.length - 3), wrongCRC]) {
      await expect(decodeSharedCard(`gz1.${bytes.toString("base64url")}`)).rejects.toThrow("Invalid compressed")
    }
  })
  it("reports unsupported decompression instead of opening a partial card", async () => {
    vi.stubGlobal("DecompressionStream", undefined)
    await expect(decodeSharedCard(compressedToken(JSON.stringify(createSharedCard([pick()], sharedAt))))).rejects.toThrow("cannot open compressed")
  })
  it("rejects aggregate payload size and an oversized uncompressed fallback without truncation", async () => {
    const huge = Array.from({ length: MAX_SHARED_PICKS }, (_, i) => pick({ eventId: `e-${i}`, reason: "⛳".repeat(2048), opponent: "A".repeat(1024) }))
    expect(() => createSharedCard(huge, sharedAt)).toThrow("data-size limit")
    vi.stubGlobal("CompressionStream", undefined)
    const large = Array.from({ length: MAX_SHARED_PICKS }, (_, i) => pick({ eventId: `e-${i}`, reason: "A".repeat(2048) }))
    await expect(encodeSharedCard(createSharedCard(large, sharedAt))).rejects.toThrow("Share fewer")
    expect(large).toHaveLength(MAX_SHARED_PICKS)
  })
})
