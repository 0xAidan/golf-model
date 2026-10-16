import { getReadOnlyJson } from "@/features/operator-data/operator-api"

export type GenerationMarket = { id: string; label: string; supported: boolean; reason?: string }
export type MarketGenerationPolicy = {
  schema_version: "market-generation-policy/v1"; state: "ready" | "unavailable";
  configured: boolean; editing_available: boolean; auth_configured: boolean; revision: string; enabled_markets: string[];
  supported_markets: GenerationMarket[]; applies_to: "future_generation"; note: string;
  error?: { code: string; message: string };
}
export type GenerationErrorCode = "auth" | "write_unavailable" | "conflict" | "unconfirmed" | "validation"
export class MarketGenerationError extends Error {
  code: GenerationErrorCode
  constructor(code: GenerationErrorCode, message: string) { super(message); this.name = "MarketGenerationError"; this.code = code }
}
const path = "/api/market-generation-policy"
const record = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v)
const strings = (v: unknown): v is string[] => Array.isArray(v) && v.every(s => typeof s === "string")
export const sameMarkets = (a: readonly string[], b: readonly string[]) => a.length === b.length && a.every(id => b.includes(id))
export function readMarketGenerationPolicy(value: unknown): MarketGenerationPolicy {
  if (!record(value) || value.schema_version !== "market-generation-policy/v1" || !["ready", "unavailable"].includes(String(value.state)) || typeof value.configured !== "boolean" || typeof value.editing_available !== "boolean" || typeof value.auth_configured !== "boolean" || typeof value.revision !== "string" || !value.revision || value.applies_to !== "future_generation" || typeof value.note !== "string" || !strings(value.enabled_markets) || new Set(value.enabled_markets).size !== value.enabled_markets.length || !Array.isArray(value.supported_markets) || !value.supported_markets.every(m => record(m) && typeof m.id === "string" && !!m.id && typeof m.label === "string" && typeof m.supported === "boolean" && (m.reason === undefined || typeof m.reason === "string"))) throw new Error("The generation policy response is incomplete.")
  const markets = value.supported_markets as GenerationMarket[]
  if (new Set(markets.map(m => m.id)).size !== markets.length || value.enabled_markets.some(id => !markets.some(m => m.id === id && m.supported))) throw new Error("The generation policy contains unsupported selections.")
  return value as unknown as MarketGenerationPolicy
}
export const getMarketGenerationPolicy = async (signal?: AbortSignal) => readMarketGenerationPolicy(await getReadOnlyJson<unknown>(path, signal))

/** A save is confirmed only after a separate GET agrees with the revision and selections. */
export async function saveMarketGenerationPolicy(value: { enabled_markets: string[]; expected_revision: string }, apiKey: string): Promise<MarketGenerationPolicy> {
  if (!apiKey.trim()) throw new MarketGenerationError("auth", "Enter an operator API key to save.")
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), 20_000)
  let response: Response
  try {
    response = await fetch(path, { method: "PATCH", credentials: "same-origin", signal: controller.signal,
      headers: { "Content-Type": "application/json", "x-api-key": apiKey.trim() }, body: JSON.stringify(value) })
    if (response.status === 401 || response.status === 403) throw new MarketGenerationError("auth", "Operator access is required. Enter a valid API key to save.")
    if (response.status === 503) {
      let body: unknown
      try { body = await response.json() } catch { /* A failed server can return a non-JSON body. */ }
      const authMissing = record(body) && record(body.detail) && body.detail.code === "write_auth_unconfigured"
      throw new MarketGenerationError("write_unavailable", authMissing
        ? "Saving is unavailable on this server. An operator must configure market-generation write access before a policy can be saved."
        : "Saving is unavailable on this server. Reload the saved policy and try again when the service is available.")
    }
    if (response.status === 409) throw new MarketGenerationError("conflict", "The saved policy changed while you were editing. Reload and review it before saving again.")
    if (response.status === 422) throw new MarketGenerationError("validation", "The server rejected this selection. Reload the supported markets and review your draft.")
    if (!response.ok) throw new MarketGenerationError("unconfirmed", "The save could not be confirmed. Reload the saved policy before trying again.")
    const acknowledgement = readMarketGenerationPolicy(await response.json())
    const readback = await getMarketGenerationPolicy(controller.signal)
    if (acknowledgement.state !== "ready" || !acknowledgement.configured || readback.state !== "ready" || !readback.configured || readback.revision !== acknowledgement.revision || !sameMarkets(readback.enabled_markets, value.enabled_markets) || !sameMarkets(acknowledgement.enabled_markets, value.enabled_markets)) throw new MarketGenerationError("unconfirmed", "The server policy differs from this save. Reload the saved policy to review its current revision.")
    return readback
  } catch (error) {
    if (error instanceof MarketGenerationError) throw error
    throw new MarketGenerationError("unconfirmed", "The save could not be confirmed. It may have reached the server. Reload the saved policy before trying again.")
  } finally { window.clearTimeout(timeout) }
}
