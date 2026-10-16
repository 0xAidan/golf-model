import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { MarketGenerationControls } from "./market-generation-controls"
import type { MarketGenerationPolicy } from "./market-generation-api"
import { CARD_KEY, VISIBLE_MARKETS_KEY } from "./market-rows"

const families = [ ["72h", "72 holes"], ["18h", "18 holes"], ["group", "Groups"], ["outright", "Outrights"], ["top5", "Top 5"], ["top10", "Top 10"], ["top20", "Top 20"], ["frl", "First-round leader"] ]
function policy(overrides: Partial<MarketGenerationPolicy> = {}): MarketGenerationPolicy {
  return { schema_version: "market-generation-policy/v1", state: "ready", configured: true, editing_available: true, auth_configured: true, revision: "r1", enabled_markets: ["72h", "top20"], supported_markets: [...families.map(([id,label]) => ({id,label,supported:true})), ...[ ["make_cut","Make cut"], ["miss_cut","Miss cut"], ["top15","Top 15"] ].map(([id,label]) => ({id,label,supported:false,reason:"No supported priced generation contract."}))], applies_to: "future_generation", note: "Prices and existing eligibility gates still apply.", ...overrides }
}
let client: QueryClient
let server: MarketGenerationPolicy
let fetchMock: ReturnType<typeof vi.fn>
let patchStatus: number
const patches = () => fetchMock.mock.calls.filter(([,init]) => init?.method === "PATCH")
function renderControls() {
  client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  return render(<QueryClientProvider client={client}><MarketGenerationControls/></QueryClientProvider>)
}
async function openControls(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByText("Market generation"))
  await screen.findByRole("checkbox", { name: "Generate 72 holes" })
}
beforeEach(() => {
  localStorage.clear()
  localStorage.setItem(VISIBLE_MARKETS_KEY, '["72h"]')
  localStorage.setItem(CARD_KEY, '[{"preserved":"card"}]')
  server = policy(); patchStatus = 200
  fetchMock = vi.fn().mockImplementation(async (_url: string, init?: RequestInit) => {
    if (init?.method === "PATCH") {
      if (patchStatus !== 200) return { ok: false, status: patchStatus }
      server = { ...server, configured: true, revision: "r2", enabled_markets: JSON.parse(String(init.body)).enabled_markets }
    }
    return { ok: true, status: 200, json: async () => server }
  })
  vi.stubGlobal("fetch", fetchMock)
})
afterEach(() => { cleanup(); client?.clear(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

describe("saved market generation controls", () => {
  it("loads only when opened and does not save a changed selection until explicit authenticated Save", async () => {
    const user = userEvent.setup()
    const localWrites = vi.spyOn(localStorage, "setItem")
    const sessionWrites = vi.spyOn(sessionStorage, "setItem")
    renderControls()
    expect(fetchMock).not.toHaveBeenCalled()
    await openControls(user)
    expect(screen.getByRole("checkbox", { name: "Generate 72 holes" })).toBeChecked()
    await user.click(screen.getByRole("checkbox", { name: "Generate Top 20" }))
    expect(patches()).toHaveLength(0)
    expect(screen.getByRole("button", { name: "Save generation policy" })).toBeDisabled()
    await user.type(screen.getByLabelText("Operator API key"), "fixture-key")
    await user.click(screen.getByRole("button", { name: "Save generation policy" }))
    expect(await screen.findByRole("status")).toHaveTextContent("saved and confirmed")
    expect(patches()).toHaveLength(1)
    expect(JSON.parse(patches()[0][1].body)).toEqual({ enabled_markets: ["72h"], expected_revision: "r1" })
    expect(patches()[0][1].headers["x-api-key"]).toBe("fixture-key")
    expect(fetchMock.mock.calls.map(([,init]) => init.method)).toEqual(["GET","PATCH","GET"])
    expect(screen.getByLabelText("Operator API key")).toHaveValue("")
    expect(localStorage.getItem(VISIBLE_MARKETS_KEY)).toBe('["72h"]')
    expect(localWrites).not.toHaveBeenCalled()
    expect(sessionWrites).not.toHaveBeenCalled()
    expect(localStorage.getItem(CARD_KEY)).toBe('[{"preserved":"card"}]')
  })

  it("saves an empty selection as no future market selections without restoring defaults", async () => {
    server = policy({ configured: false, revision: "unconfigured", enabled_markets: families.map(([id]) => id) })
    const user = userEvent.setup()
    renderControls(); await openControls(user)
    expect(screen.getByText("Using existing generation defaults.")).toBeInTheDocument()
    for (const [,label] of families) await user.click(screen.getByRole("checkbox", { name: `Generate ${label}` }))
    expect(screen.getByText(/rankings without market selections/)).toBeInTheDocument()
    await user.type(screen.getByLabelText("Operator API key"), "key")
    await user.click(screen.getByRole("button", { name: "Save generation policy" }))
    await screen.findByText(/Generation policy saved and confirmed/)
    expect(JSON.parse(patches()[0][1].body)).toEqual({ enabled_markets: [], expected_revision: "unconfigured" })
    expect(screen.getAllByRole("checkbox").every(c => !(c as HTMLInputElement).checked)).toBe(true)
    expect(screen.getByText("0 selected")).toBeInTheDocument()
  })

  it("keeps unsupported markets disabled and explains their capability gap", async () => {
    const user = userEvent.setup(); renderControls(); await openControls(user)
    for (const label of ["Make cut","Miss cut","Top 15"]) expect(screen.getByRole("checkbox", { name: `Generate ${label}` })).toBeDisabled()
    expect(screen.getAllByText("No supported priced generation contract.")).toHaveLength(3)
    expect(patches()).toHaveLength(0)
  })

  it("preserves a draft after failed authorization, clears the key and retries only when explicitly saved", async () => {
    patchStatus = 401
    const user = userEvent.setup(); renderControls(); await openControls(user)
    await user.click(screen.getByRole("checkbox", { name: "Generate Top 20" }))
    await user.type(screen.getByLabelText("Operator API key"), "wrong-key")
    await user.click(screen.getByRole("button", { name: "Save generation policy" }))
    expect(await screen.findByRole("alert")).toHaveTextContent("Operator access is required")
    expect(screen.getByRole("checkbox", { name: "Generate Top 20" })).not.toBeChecked()
    expect(screen.getByLabelText("Operator API key")).toHaveValue("")
    expect(patches()).toHaveLength(1)
    patchStatus = 200
    await user.type(screen.getByLabelText("Operator API key"), "replacement-key")
    await user.click(screen.getByRole("button", { name: "Save generation policy" }))
    await screen.findByText(/saved and confirmed/)
    expect(patches()).toHaveLength(2)
  })

  it("keeps the conflicted draft until explicit reload, then saves against the new server revision", async () => {
    patchStatus = 409
    const user = userEvent.setup(); renderControls(); await openControls(user)
    await user.click(screen.getByRole("checkbox", { name: "Generate Top 20" }))
    server = policy({ revision: "r9", enabled_markets: ["18h"] })
    await user.type(screen.getByLabelText("Operator API key"), "key")
    await user.click(screen.getByRole("button", { name: "Save generation policy" }))
    expect(await screen.findByRole("alert")).toHaveTextContent("saved policy changed")
    expect(screen.getByRole("checkbox", { name: "Generate 72 holes" })).toBeChecked()
    expect(screen.getByRole("checkbox", { name: "Generate 18 holes" })).not.toBeChecked()
    expect(JSON.parse(patches()[0][1].body).expected_revision).toBe("r1")
    await user.click(screen.getByRole("button", { name: "Reload and discard draft" }))
    await waitFor(() => expect(screen.getByRole("checkbox", { name: "Generate 18 holes" })).toBeChecked())
    expect(screen.getByRole("checkbox", { name: "Generate 72 holes" })).not.toBeChecked()
    patchStatus = 200
    await user.click(screen.getByRole("checkbox", { name: "Generate Outrights" }))
    await user.type(screen.getByLabelText("Operator API key"), "key")
    await user.click(screen.getByRole("button", { name: "Save generation policy" }))
    await screen.findByText(/saved and confirmed/)
    expect(JSON.parse(patches()[1][1].body).expected_revision).toBe("r9")
  })

  it("blocks editing when server write authentication is unconfigured", async () => {
    server = policy({ editing_available: false, auth_configured: false })
    const user = userEvent.setup(); renderControls(); await openControls(user)
    expect(screen.getByRole("status")).toHaveTextContent("Saving is unavailable on this server")
    expect(screen.getByRole("checkbox", { name: "Generate 72 holes" })).toBeDisabled()
    expect(screen.getByLabelText("Operator API key")).toBeDisabled()
    expect(screen.getByRole("button", { name: "Save generation policy" })).toBeDisabled()
    expect(patches()).toHaveLength(0)
  })

  it("reports server write blocking without claiming the draft was saved", async () => {
    patchStatus = 503
    const user = userEvent.setup(); renderControls(); await openControls(user)
    await user.click(screen.getByRole("checkbox", { name: "Generate Top 20" }))
    await user.type(screen.getByLabelText("Operator API key"), "key")
    await user.click(screen.getByRole("button", { name: "Save generation policy" }))
    expect(await screen.findByRole("alert")).toHaveTextContent("Saving is unavailable")
    expect(screen.getByRole("button", { name: "Save generation policy" })).toBeDisabled()
    expect(screen.queryByText(/saved and confirmed/)).not.toBeInTheDocument()
    expect(patches()).toHaveLength(1)
  })

  it.each(["unavailable", "malformed"])("does not invent an editable policy from %s server data", async state => {
    if (state === "unavailable") server = policy({ state: "unavailable", revision: "unavailable", enabled_markets: [], editing_available: false })
    else fetchMock.mockResolvedValue({ ok: true, json: async () => ({ schema_version: "bad", enabled_markets: [] }) })
    const user = userEvent.setup(); renderControls()
    await user.click(screen.getByText("Market generation"))
    expect(await screen.findByRole("alert")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Save generation policy" })).not.toBeInTheDocument()
    expect(patches()).toHaveLength(0)
  })

  it("leaves the save uncertain when the acknowledgement cannot be confirmed by readback", async () => {
    let reads = 0
    fetchMock.mockImplementation(async (_url: string, init?: RequestInit) => {
      if (init?.method === "PATCH") return { ok: true, status: 200, json: async () => policy({ revision: "r2", enabled_markets: ["72h"] }) }
      if (++reads > 1) throw new Error("Readback unavailable")
      return { ok: true, json: async () => server }
    })
    const user = userEvent.setup(); renderControls(); await openControls(user)
    await user.click(screen.getByRole("checkbox", { name: "Generate Top 20" }))
    await user.type(screen.getByLabelText("Operator API key"), "key")
    await user.click(screen.getByRole("button", { name: "Save generation policy" }))
    expect(await screen.findByRole("alert")).toHaveTextContent("may have reached the server")
    expect(screen.queryByText(/saved and confirmed/)).not.toBeInTheDocument()
    expect(screen.getByRole("checkbox", { name: "Generate Top 20" })).not.toBeChecked()
    expect(screen.getByRole("button", { name: "Save generation policy" })).toBeDisabled()
    expect(patches()).toHaveLength(1)
  })

  it("shows loading until a saved server policy is available", async () => {
    let finish: (value: unknown) => void = () => undefined
    fetchMock.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    const user = userEvent.setup(); renderControls()
    await user.click(screen.getByText("Market generation"))
    expect(await screen.findByRole("status")).toHaveTextContent("Reading saved generation policy")
    expect(screen.queryByRole("button", { name: "Save generation policy" })).not.toBeInTheDocument()
    finish({ ok: true, json: async () => server })
    expect(await screen.findByRole("checkbox", { name: "Generate 72 holes" })).toBeChecked()
    expect(patches()).toHaveLength(0)
  })

  it("can recover a failed read without losing browser preferences or writing a policy", async () => {
    fetchMock.mockRejectedValueOnce(new Error("Read unavailable"))
    const user = userEvent.setup(); renderControls()
    await user.click(screen.getByText("Market generation"))
    expect(await screen.findByRole("alert")).toHaveTextContent("could not be loaded")
    await user.click(screen.getByRole("button", { name: "Reload generation policy" }))
    expect(await screen.findByRole("checkbox", { name: "Generate 72 holes" })).toBeChecked()
    expect(patches()).toHaveLength(0)
    expect(localStorage.getItem(VISIBLE_MARKETS_KEY)).toBe('["72h"]')
  })

  it("clears the in-memory key when controls close while preserving the draft", async () => {
    const user = userEvent.setup(); renderControls(); await openControls(user)
    await user.click(screen.getByRole("checkbox", { name: "Generate Top 20" }))
    await user.type(screen.getByLabelText("Operator API key"), "private-key")
    await user.click(screen.getByText("Market generation"))
    await user.click(screen.getByText("Market generation"))
    expect(await screen.findByLabelText("Operator API key")).toHaveValue("")
    expect(screen.getByRole("checkbox", { name: "Generate Top 20" })).not.toBeChecked()
    expect(patches()).toHaveLength(0)
  })

  it("discards unsaved edits and key material without a write", async () => {
    const user = userEvent.setup(); renderControls(); await openControls(user)
    await user.click(screen.getByRole("checkbox", { name: "Generate Top 20" }))
    await user.type(screen.getByLabelText("Operator API key"), "discard-key")
    await user.click(screen.getByRole("button", { name: "Discard draft" }))
    expect(screen.getByRole("checkbox", { name: "Generate Top 20" })).toBeChecked()
    expect(screen.getByLabelText("Operator API key")).toHaveValue("")
    expect(patches()).toHaveLength(0)
  })
})
