import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { getMarketGenerationPolicy, readMarketGenerationPolicy, saveMarketGenerationPolicy, type MarketGenerationPolicy } from "./market-generation-api"

const policy = (overrides: Partial<MarketGenerationPolicy> = {}): MarketGenerationPolicy => ({ schema_version: "market-generation-policy/v1", state: "ready", configured: false, editing_available: true, auth_configured: true, revision: "unconfigured", enabled_markets: ["72h", "top20"], supported_markets: [{ id: "72h", label: "72 holes", supported: true }, { id: "top20", label: "Top 20", supported: true }, { id: "make_cut", label: "Make cut", supported: false, reason: "No priced make-cut provider contract." }], applies_to: "future_generation", note: "Future runs only.", ...overrides })
let fetchMock: ReturnType<typeof vi.fn>
beforeEach(() => { fetchMock = vi.fn(); vi.stubGlobal("fetch", fetchMock) })
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })

describe("market generation API contract", () => {
  it("retains an explicitly empty policy instead of restoring defaults", () => {
    expect(readMarketGenerationPolicy(policy({ configured: true, revision: "r2", enabled_markets: [] })).enabled_markets).toEqual([])
  })
  it.each([
    { schema_version: 1 }, { enabled_markets: ["72h", "72h"] }, { enabled_markets: ["make_cut"] },
    { enabled_markets: ["unknown"] }, { editing_available: undefined }, { supported_markets: {} },
  ])("rejects incomplete or unsupported server policy data (%j)", change => {
    expect(() => readMarketGenerationPolicy({ ...policy(), ...change })).toThrow()
  })
  it("sends the exact draft revision and confirms the acknowledged revision with a separate GET", async () => {
    const saved = policy({ configured: true, revision: "r2", enabled_markets: [] })
    fetchMock.mockResolvedValue({ ok: true, status: 200, json: async () => saved })
    expect(await saveMarketGenerationPolicy({ enabled_markets: [], expected_revision: "unconfigured" }, " fixture-key ")).toEqual(saved)
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(fetchMock.mock.calls[0][0]).toBe("/api/market-generation-policy")
    const init = fetchMock.mock.calls[0][1]
    expect(init).toMatchObject({ method: "PATCH", credentials: "same-origin", headers: { "Content-Type": "application/json", "x-api-key": "fixture-key" } })
    expect(JSON.parse(init.body)).toEqual({ enabled_markets: [], expected_revision: "unconfigured" })
    expect(fetchMock.mock.calls[1][1].method).toBe("GET")
  })
  it.each([[401, "auth"], [403, "auth"], [409, "conflict"], [503, "write_unavailable"], [422, "validation"]])("handles HTTP %s without retrying a write", async (status, code) => {
    fetchMock.mockResolvedValue({ ok: false, status })
    await expect(saveMarketGenerationPolicy({ enabled_markets: [], expected_revision: "r1" }, "key")).rejects.toMatchObject({ code })
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
  it("does not claim success when readback has a different revision or market set", async () => {
    fetchMock.mockResolvedValueOnce({ ok: true, status: 200, json: async () => policy({ configured: true, revision: "r2", enabled_markets: [] }) })
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => policy({ configured: true, revision: "r3", enabled_markets: ["72h"] }) })
    await expect(saveMarketGenerationPolicy({ enabled_markets: [], expected_revision: "r1" }, "key")).rejects.toMatchObject({ code: "unconfirmed" })
    expect(fetchMock.mock.calls.filter(([,init]) => init.method === "PATCH")).toHaveLength(1)
  })
  it.each(["write_auth_unconfigured", "policy_unavailable"])("distinguishes server auth configuration from policy service failures (%s)", async code => {
    fetchMock.mockResolvedValue({ ok: false, status: 503, json: async () => ({ detail: { code } }) })
    const saving = saveMarketGenerationPolicy({ enabled_markets: [], expected_revision: "r1" }, "key")
    await expect(saving).rejects.toThrow(code === "write_auth_unconfigured" ? /configure market-generation write access/ : /try again when the service is available/)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
  it("treats a connection failure as an uncertain save and never retries the PATCH", async () => {
    fetchMock.mockRejectedValue(new TypeError("Network failure"))
    await expect(saveMarketGenerationPolicy({ enabled_markets: [], expected_revision: "r1" }, "key")).rejects.toMatchObject({ code: "unconfirmed" })
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
  it("preserves an unavailable read response for a blocked editing state", async () => {
    const value = policy({ state: "unavailable", editing_available: false, revision: "unavailable", enabled_markets: [] })
    fetchMock.mockResolvedValue({ ok: true, json: async () => value })
    expect(await getMarketGenerationPolicy()).toEqual(value)
  })
  it("does not attempt a write without an operator key", async () => {
    await expect(saveMarketGenerationPolicy({ enabled_markets: [], expected_revision: "r1" }, " ")).rejects.toMatchObject({ code: "auth" })
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
