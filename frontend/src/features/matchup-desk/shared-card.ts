import { MARKET_FAMILIES, MARKET_LABELS, marketFamily, type SavedPick } from "./market-rows"

/** These are untrusted, user-shared quote snapshots, never verified wagers. */
export type SharedCard = { version: 1; createdAt: string; picks: SavedPick[] }
export const MAX_SHARED_PICKS = 32
export const MAX_SHARED_TOKEN_LENGTH = 48 * 1024
export const MAX_SHARED_JSON_BYTES = 128 * 1024

const requiredPickKeys = [
  "id", "eventId", "eventName", "mode", "market", "marketType", "round", "player", "playerKey",
  "opponent", "book", "odds", "probability", "ev", "reason", "lineAt", "snapshotAt", "eligible", "savedAt",
] as const
const allowedPickKeys = new Set<string>([...requiredPickKeys, "impliedProbability"])
const markets = new Set<string>(MARKET_FAMILIES)
const modes = new Set(["upcoming", "live", "past"])
const encoder = new TextEncoder()

function fail(message: string): never { throw new Error(message) }
function record(value: unknown, label: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) fail(`Invalid ${label}.`)
  const prototype = Object.getPrototypeOf(value)
  if (prototype !== Object.prototype && prototype !== null) fail(`Invalid ${label}.`)
  return value as Record<string, unknown>
}
function text(value: unknown, label: string, maximum: number, required = true, multiline = false): string {
  if (typeof value !== "string" || value.length > maximum || (required && !value.trim())) fail(`Invalid ${label}.`)
  for (const character of value) {
    const code = character.codePointAt(0)!
    if ((code < 32 || code === 127) && !(multiline && [9, 10, 13].includes(code))) fail(`Invalid ${label}.`)
  }
  return value
}
function timestamp(value: unknown, label: string, nullable = false, originalTime = false): void {
  if (nullable && value === null) return
  const raw = text(value, label, 64)
  const match = raw.match(/^(\d{4})-(\d{2})-(\d{2})([T ])(\d{2}):(\d{2}):(\d{2})(?:\.\d{1,9})?(Z|[+-]\d{2}:\d{2})?$/)
  if (!match || (!originalTime && (match[4] !== "T" || !match[8]))) fail(`Invalid ${label}.`)
  const [, year, month, day, , hour, minute, second, zone] = match
  const y = Number(year), m = Number(month), d = Number(day)
  const leap = y % 4 === 0 && (y % 100 !== 0 || y % 400 === 0)
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
  if (m < 1 || m > 12 || d < 1 || d > days[m - 1] || Number(hour) > 23 || Number(minute) > 59 || Number(second) > 59) fail(`Invalid ${label}.`)
  if (zone && zone !== "Z") {
    const zh = Number(zone.slice(1, 3)), zm = Number(zone.slice(4, 6))
    if (zh > 14 || zm > 59 || (zh === 14 && zm !== 0)) fail(`Invalid ${label}.`)
  }
}
function probability(value: unknown, label: string): void {
  if (value !== null && (typeof value !== "number" || !Number.isFinite(value) || value < 0 || value > 1)) fail(`Invalid ${label}.`)
}
function validatePick(value: unknown): SavedPick {
  const row = record(value, "saved pick")
  if (requiredPickKeys.some(key => !Object.hasOwn(row, key)) || Object.keys(row).some(key => !allowedPickKeys.has(key))) fail("Unsupported saved-pick fields.")
  text(row.id, "quote identity", 4096)
  for (const key of ["eventId", "eventName", "player", "playerKey", "book"] as const) text(row[key], key, 256)
  text(row.opponent, "opponent", 1024, false)
  text(row.marketType, "market type", 128)
  text(row.round, "round", 32, false)
  text(row.reason, "reason", 2048, false, true)
  text(row.mode, "mode", 16)
  text(row.market, "market", 16)
  if (!modes.has(row.mode as string) || !markets.has(row.market as string)) fail("Unsupported quote mode or market.")
  const family = marketFamily(row.marketType)
  // Older saved/shared placement quotes used the original catch-all family.
  // Accept those unchanged; the original quote identity still verifies below.
  const legacyPlacement = row.market === "other" && !["72h", "18h", "group", "other"].includes(family)
  if (family !== row.market && !legacyPlacement) fail("Conflicting market duration.")
  const odds = text(row.odds, "price", 32)
  if (!/^[+-]?\d+(?:\.\d+)?$/.test(odds) || !Number.isFinite(Number(odds)) || Math.abs(Number(odds)) < 100) fail("Invalid original price.")
  probability(row.probability, "model probability")
  if (Object.hasOwn(row, "impliedProbability")) probability(row.impliedProbability, "book probability")
  if (row.ev !== null && (typeof row.ev !== "number" || !Number.isFinite(row.ev))) fail("Invalid expected value.")
  if (typeof row.eligible !== "boolean") fail("Invalid saved eligibility flag.")
  timestamp(row.lineAt, "quote timestamp", true, true)
  timestamp(row.snapshotAt, "snapshot timestamp", true, true)
  timestamp(row.savedAt, "saved timestamp")

  // Group/market identity is embedded in the existing DeskRow key. Preserve it
  // byte-for-byte and reject contradictions rather than reconstructing the key.
  let identity: unknown
  try { identity = JSON.parse(row.id as string) } catch { fail("Invalid quote identity.") }
  if (!Array.isArray(identity) || ![9, 10].includes(identity.length) || identity.some(v => typeof v !== "string" || v.length > 1024)) fail("Invalid quote identity.")
  const matches: [number, keyof SavedPick][] = [[0, "eventId"], [1, "mode"], [2, "marketType"], [3, "round"], [5, "playerKey"], [7, "book"], [8, "odds"]]
  if (matches.some(([index, key]) => identity[index] !== row[key])) fail("Conflicting quote identity.")
  if (row.market === "18h" && !/^[1-4]$/.test(row.round as string)) fail("An 18-hole quote needs an explicit round.")
  if (row.market === "group" && !identity[4].trim() && !identity[9]?.trim()) fail("A group quote needs its original group or market identity.")
  return { ...row } as SavedPick
}
function validateCard(value: unknown): SharedCard {
  const card = record(value, "shared card")
  if (card.version !== 1 || Object.keys(card).length !== 3 || !["version", "createdAt", "picks"].every(key => Object.hasOwn(card, key))) fail("Unsupported shared-card version or fields.")
  timestamp(card.createdAt, "shared timestamp")
  if (!Array.isArray(card.picks) || card.picks.length < 1 || card.picks.length > MAX_SHARED_PICKS) fail(`Share between 1 and ${MAX_SHARED_PICKS} saved picks.`)
  const picks = Array.from(card.picks, validatePick)
  if (new Set(picks.map(pick => JSON.stringify(JSON.parse(pick.id)))).size !== picks.length) fail("Duplicate saved quotes in shared card.")
  const result: SharedCard = { version: 1, createdAt: card.createdAt as string, picks }
  if (encoder.encode(JSON.stringify(result)).byteLength > MAX_SHARED_JSON_BYTES) fail("Shared card exceeds the data-size limit.")
  return result
}

export function createSharedCard(picks: SavedPick[], createdAt = new Date().toISOString()): SharedCard {
  return validateCard({ version: 1, createdAt, picks })
}

function toBase64Url(bytes: Uint8Array): string {
  let binary = ""
  for (const byte of bytes) binary += String.fromCharCode(byte)
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "")
}
function fromBase64Url(value: string): Uint8Array<ArrayBuffer> {
  if (!value || !/^[A-Za-z0-9_-]+$/.test(value) || value.length % 4 === 1) fail("Malformed shared-card encoding.")
  let binary: string
  try { binary = atob(value.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - value.length % 4) % 4)) } catch { fail("Malformed shared-card encoding.") }
  const bytes = Uint8Array.from(binary, character => character.charCodeAt(0))
  if (toBase64Url(bytes) !== value) fail("Noncanonical shared-card encoding.")
  return bytes
}
function byteStream(bytes: Uint8Array<ArrayBuffer>): ReadableStream<BufferSource> {
  return new ReadableStream<BufferSource>({ start(controller) { controller.enqueue(bytes); controller.close() } })
}
async function boundedBytes(stream: ReadableStream<Uint8Array>, maximum: number): Promise<Uint8Array<ArrayBuffer>> {
  const reader = stream.getReader()
  const chunks: Uint8Array[] = []
  let size = 0
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      size += value.byteLength
      if (size > maximum) fail("Shared card exceeds the data-size limit.")
      chunks.push(value)
    }
  } catch (error) {
    await reader.cancel().catch(() => undefined)
    throw error
  } finally { reader.releaseLock() }
  const result = new Uint8Array(size)
  let offset = 0
  for (const chunk of chunks) { result.set(chunk, offset); offset += chunk.byteLength }
  return result
}

/** Returns a token for /shared-card#card=TOKEN. No URL, storage or network access. */
export async function encodeSharedCard(card: SharedCard): Promise<string> {
  const bytes = encoder.encode(JSON.stringify(validateCard(card)))
  const compressed = typeof CompressionStream !== "undefined" && typeof DecompressionStream !== "undefined"
  const body = compressed ? await boundedBytes(byteStream(bytes).pipeThrough(new CompressionStream("gzip")), MAX_SHARED_JSON_BYTES) : bytes
  const token = `${compressed ? "gz1" : "json1"}.${toBase64Url(body)}`
  if (token.length > MAX_SHARED_TOKEN_LENGTH) fail("Shared link is too large. Share fewer saved picks.")
  return token
}

/** Decode only a token, never a URL. All fields remain untrusted snapshot data. */
export async function decodeSharedCard(token: string): Promise<SharedCard> {
  if (typeof token !== "string" || token.length > MAX_SHARED_TOKEN_LENGTH) fail("Shared link exceeds the size limit.")
  const match = token.match(/^(gz1|json1)\.([A-Za-z0-9_-]+)$/)
  if (!match) fail("Unsupported or malformed shared link.")
  let bytes = fromBase64Url(match[2])
  if (match[1] === "gz1") {
    if (typeof DecompressionStream === "undefined") fail("This browser cannot open compressed shared cards.")
    try { bytes = await boundedBytes(byteStream(bytes).pipeThrough(new DecompressionStream("gzip")), MAX_SHARED_JSON_BYTES) }
    catch (error) {
      if (error instanceof Error && error.message === "Shared card exceeds the data-size limit.") throw error
      fail("Invalid compressed shared card.")
    }
  }
  if (bytes.byteLength > MAX_SHARED_JSON_BYTES) fail("Shared card exceeds the data-size limit.")
  let value: unknown
  try {
    const json = new TextDecoder("utf-8", { fatal: true }).decode(bytes)
    value = JSON.parse(json)
    // Our encoders emit canonical compact JSON. This also rejects duplicate
    // object keys instead of silently accepting JSON.parse's last value.
    if (JSON.stringify(value) !== json) fail("Noncanonical shared-card data.")
  } catch { fail("Malformed shared-card data.") }
  return validateCard(value)
}

function percent(value: number | null, signed = false): string {
  if (value === null) return "Unavailable"
  const scaled = value * 100
  if (!Number.isFinite(scaled)) return "Unavailable"
  return `${signed && value > 0 ? "+" : ""}${Number(scaled.toFixed(2))}%`
}
export function formatSharedPicksText(card: SharedCard): string {
  const checked = validateCard(card)
  const marketLabels = { ...MARKET_LABELS, group: "Group", other: "Other / unspecified duration" }
  const lines = ["Golf shared card", `Shared: ${checked.createdAt}`, "Saved prices are unverified and not live; availability may have changed."]
  for (const [index, pick] of checked.picks.entries()) {
    let market = `${marketLabels[pick.market]}${pick.round ? ` · Round ${pick.round}` : ""}`
    if (pick.market === "group") {
      const identity: string[] = JSON.parse(pick.id)
      market += ` · Contract ${identity[9]?.trim() ? identity[9] : identity[4]}`
    }
    lines.push("", `${index + 1}. ${pick.eventName}`, market,
      `${pick.player}${pick.opponent ? ` vs ${pick.opponent}` : ""}`,
      `${pick.book} · ${pick.odds}`,
      `Model probability: ${percent(pick.probability)} · EV: ${percent(pick.ev, true)}`,
      `Quote time: ${pick.lineAt ?? "Unavailable"}`, `Snapshot time: ${pick.snapshotAt ?? "Unavailable"}`)
    if (pick.reason.trim()) lines.push(`Reason: ${pick.reason}`)
  }
  return lines.join("\n")
}
