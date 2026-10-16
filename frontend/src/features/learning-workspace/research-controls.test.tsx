import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { ResearchControls } from "./research-controls"

let client: QueryClient
let fetchMock: ReturnType<typeof vi.fn>
let saved: unknown
let patchStatus: number
function renderControls() {
  client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  return render(<QueryClientProvider client={client}><ResearchControls/></QueryClientProvider>)
}
const patchCalls = () => fetchMock.mock.calls.filter(([, init]) => init?.method === "PATCH")
beforeEach(() => {
  saved = { autoresearch_effort: "standard", optuna_trials_per_cycle: 10, unrelated_setting: "keep" }
  patchStatus = 200
  fetchMock = vi.fn().mockImplementation(async (_url: string, init?: RequestInit) => {
    if (init?.method === "PATCH") {
      if (patchStatus === 200) saved = { ...(saved as object), ...JSON.parse(String(init.body)) }
      return { ok: patchStatus === 200, status: patchStatus, json: async () => saved }
    }
    return { ok: true, status: 200, json: async () => saved }
  })
  vi.stubGlobal("fetch", fetchMock)
})
afterEach(() => { cleanup(); client?.clear(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

describe("authenticated research settings", () => {
  it("reads saved settings without mutation and saves only the explicit research changes", async () => {
    const user = userEvent.setup()
    const storage = vi.spyOn(localStorage, "setItem")
    renderControls()
    await user.click(screen.getByText("Research controls"))
    const effort = await screen.findByRole("combobox", { name: "Research effort" })
    expect(effort).toHaveValue("standard")
    expect(screen.getByRole("button", { name: "Save research settings" })).toBeDisabled()
    expect(patchCalls()).toHaveLength(0)
    await user.selectOptions(effort, "max")
    const trials = screen.getByRole("spinbutton", { name: "Trials per cycle" })
    await user.clear(trials)
    await user.type(trials, "25")
    await user.type(screen.getByLabelText("Operator API key"), "fixture-key")
    await user.click(screen.getByRole("button", { name: "Save research settings" }))
    expect(await screen.findByRole("status")).toHaveTextContent("Research settings saved.")
    expect(patchCalls()).toHaveLength(1)
    const [url, init] = patchCalls()[0]
    expect(url).toBe("/api/autoresearch/settings")
    expect(init).toMatchObject({ method: "PATCH", credentials: "same-origin", headers: { "Content-Type": "application/json", "x-api-key": "fixture-key" } })
    expect(JSON.parse(init.body)).toEqual({ autoresearch_effort: "max", optuna_trials_per_cycle: 25 })
    expect(saved).toMatchObject({ unrelated_setting: "keep" })
    expect(screen.getByLabelText("Operator API key")).toHaveValue("")
    expect(storage).not.toHaveBeenCalled()
    expect(screen.getByRole("button", { name: "Save research settings" })).toBeDisabled()
  })

  it("keeps the draft after an authorization failure and permits a deliberate retry with a key", async () => {
    patchStatus = 401
    const user = userEvent.setup()
    renderControls()
    await user.click(screen.getByText("Research controls"))
    await user.selectOptions(await screen.findByRole("combobox", { name: "Research effort" }), "light")
    await user.click(screen.getByRole("button", { name: "Save research settings" }))
    expect(await screen.findByRole("alert")).toHaveTextContent("Operator access is required.")
    expect(screen.getByRole("combobox", { name: "Research effort" })).toHaveValue("light")
    expect(patchCalls()).toHaveLength(1)
    expect(patchCalls()[0][1].headers).not.toHaveProperty("x-api-key")
    patchStatus = 200
    await user.type(screen.getByLabelText("Operator API key"), "retry-key")
    await user.click(screen.getByRole("button", { name: "Save research settings" }))
    expect(await screen.findByRole("status")).toHaveTextContent("Research settings saved.")
    expect(patchCalls()).toHaveLength(2)
    expect(patchCalls()[1][1].headers["x-api-key"]).toBe("retry-key")
  })

  it("prevents invalid trial counts and discards unsaved changes without a request", async () => {
    const user = userEvent.setup()
    renderControls()
    await user.click(screen.getByText("Research controls"))
    const trials = await screen.findByRole("spinbutton", { name: "Trials per cycle" })
    await user.clear(trials)
    await user.type(trials, "51")
    expect(screen.getByRole("alert")).toHaveTextContent("Use a whole number from 1 to 50 trials.")
    expect(screen.getByRole("button", { name: "Save research settings" })).toBeDisabled()
    await user.type(screen.getByLabelText("Operator API key"), "discard-key")
    await user.click(screen.getByRole("button", { name: "Discard changes" }))
    expect(trials).toHaveValue(10)
    expect(screen.getByLabelText("Operator API key")).toHaveValue("")
    expect(patchCalls()).toHaveLength(0)
  })

  it("does not invent default settings when the server payload is incomplete", async () => {
    saved = { autoresearch_effort: "unknown", optuna_trials_per_cycle: 100 }
    const user = userEvent.setup()
    renderControls()
    await user.click(screen.getByText("Research controls"))
    expect(await screen.findByRole("alert")).toHaveTextContent("Research settings could not be loaded.")
    expect(screen.queryByRole("button", { name: "Save research settings" })).not.toBeInTheDocument()
    expect(patchCalls()).toHaveLength(0)
  })

  it("rejects an unacknowledged save rather than presenting the draft as saved", async () => {
    const user = userEvent.setup()
    fetchMock.mockImplementation(async (_url: string, init?: RequestInit) => ({ ok: true, status: 200, json: async () => saved, method: init?.method }))
    renderControls()
    await user.click(screen.getByText("Research controls"))
    await user.selectOptions(await screen.findByRole("combobox", { name: "Research effort" }), "max")
    await user.click(screen.getByRole("button", { name: "Save research settings" }))
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("The server returned different settings."))
    expect(screen.getByRole("combobox", { name: "Research effort" })).toHaveValue("max")
    expect(screen.queryByText("Research settings saved.")).not.toBeInTheDocument()
  })
})
