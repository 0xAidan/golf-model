import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query"
import { act, cleanup, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import type { LiveRefreshSnapshotResponse } from "@/lib/types"
import { LiveSnapshotProvider, useLiveSnapshot } from "./live-snapshot-provider"

const { apiMock, cacheMock } = vi.hoisted(() => ({
  apiMock: {
    getLiveRefreshStatus: vi.fn(),
    getLiveRefreshSnapshot: vi.fn(),
    getLiveRefreshSummary: vi.fn(),
  },
  cacheMock: { read: vi.fn(), readIdb: vi.fn(), write: vi.fn(), writeIdb: vi.fn() },
}))

vi.mock("@/lib/api", () => ({ api: apiMock }))
vi.mock("@/lib/warm-snapshot", () => ({ readWarmSnapshotEnvelope: cacheMock.read, writeWarmSnapshotEnvelope: cacheMock.write }))
vi.mock("@/lib/warm-snapshot-idb", () => ({ readIdbWarmSnapshotEnvelope: cacheMock.readIdb, writeIdbWarmSnapshotEnvelope: cacheMock.writeIdb }))

function Probe() {
  const data = useLiveSnapshot()
  return <output data-testid="snapshot">{JSON.stringify({
    id: data.displaySnapshot?.snapshot_id,
    authoritative: data.snapshot?.snapshot_id ?? null,
    state: data.dataState,
    dbUnavailable: data.dbUnavailable,
  })}</output>
}

function SharedStatusConsumer() {
  useQuery({ queryKey: ["live-refresh-status"], queryFn: apiMock.getLiveRefreshStatus })
  return null
}

const fresh: LiveRefreshSnapshotResponse = {
  ok: true,
  data_state: "fresh",
  snapshot: { snapshot_id: "current", generated_at: "2026-10-14T02:00:00Z" },
  age_seconds: 10,
  stale_after_seconds: 3720,
}

const clients: QueryClient[] = []

function mount({ pending = false, sharedStatus = false } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 15_000, gcTime: Infinity } } })
  clients.push(client)
  const tree = (manualRefreshPending: boolean) => <QueryClientProvider client={client}>
    <LiveSnapshotProvider manualRefreshPending={manualRefreshPending}>
      <Probe />
      {sharedStatus && <SharedStatusConsumer />}
    </LiveSnapshotProvider>
  </QueryClientProvider>
  const view = render(tree(pending))
  return { client, rerender: (manualRefreshPending: boolean) => view.rerender(tree(manualRefreshPending)) }
}

async function advance(ms = 5) {
  await act(async () => { await vi.advanceTimersByTimeAsync(ms) })
}

async function visibility(hidden: boolean) {
  vi.spyOn(document, "visibilityState", "get").mockReturnValue(hidden ? "hidden" : "visible")
  act(() => { document.dispatchEvent(new Event("visibilitychange")) })
  await advance()
}

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date("2026-10-14T02:00:10Z"))
  vi.spyOn(document, "visibilityState", "get").mockReturnValue("visible")
  vi.clearAllMocks()
  cacheMock.read.mockReturnValue(null)
  cacheMock.readIdb.mockResolvedValue(null)
  cacheMock.writeIdb.mockResolvedValue(undefined)
  apiMock.getLiveRefreshStatus.mockResolvedValue({ status: { running: true, refresh_state: "idle" } })
  apiMock.getLiveRefreshSnapshot.mockResolvedValue(fresh)
  apiMock.getLiveRefreshSummary.mockResolvedValue(fresh)
})

afterEach(() => {
  cleanup()
  clients.splice(0).forEach(client => client.clear())
  vi.restoreAllMocks()
  vi.useRealTimers()
})

describe("legacy snapshot request coordination", () => {
  it("uses one healthy snapshot request and slow status checks while the worker is idle", async () => {
    mount()
    await advance()
    await advance(30_000)
    expect(apiMock.getLiveRefreshSnapshot).toHaveBeenCalledTimes(1)
    expect(apiMock.getLiveRefreshSummary).not.toHaveBeenCalled()
    expect(apiMock.getLiveRefreshStatus).toHaveBeenCalledTimes(3)
    expect(screen.getByTestId("snapshot")).toHaveTextContent('"id":"current"')
  })

  it("keeps live-round snapshots and active refresh status updating quickly", async () => {
    apiMock.getLiveRefreshStatus.mockResolvedValue({ status: { running: true, progress: { refresh_state: "busy" } } })
    apiMock.getLiveRefreshSnapshot.mockResolvedValue({ ...fresh, snapshot: { ...fresh.snapshot, live_tournament: { active: true } } })
    mount()
    await advance()
    await advance(20_000)
    expect(apiMock.getLiveRefreshSnapshot).toHaveBeenCalledTimes(3)
    expect(apiMock.getLiveRefreshStatus).toHaveBeenCalledTimes(9)
    expect(apiMock.getLiveRefreshSummary).not.toHaveBeenCalled()
  })

  it("shares status requests with tool panels and preserves that identity during manual refresh", async () => {
    const view = mount({ sharedStatus: true })
    await advance()
    expect(apiMock.getLiveRefreshStatus).toHaveBeenCalledTimes(1)
    view.rerender(true)
    await advance(2_500)
    expect(apiMock.getLiveRefreshStatus).toHaveBeenCalledTimes(2)
    expect(view.client.getQueryCache().findAll({ queryKey: ["live-refresh-status"] })).toHaveLength(1)
    await advance(7_500)
    expect(apiMock.getLiveRefreshSnapshot).toHaveBeenCalledTimes(2)
  })

  it("loads the completed snapshot immediately when refresh progress becomes idle", async () => {
    apiMock.getLiveRefreshStatus.mockResolvedValue({ status: { running: true, refresh_state: "running" } })
    const { client } = mount()
    await advance()
    apiMock.getLiveRefreshStatus.mockResolvedValue({ status: { running: true, refresh_state: "idle" } })
    apiMock.getLiveRefreshSnapshot.mockResolvedValue({ ...fresh, snapshot: { ...fresh.snapshot, snapshot_id: "completed-cycle" } })
    await act(async () => { await client.invalidateQueries({ queryKey: ["live-refresh-status"] }) })
    await advance(20)
    expect(apiMock.getLiveRefreshSnapshot).toHaveBeenCalledTimes(2)
    expect(screen.getByTestId("snapshot")).toHaveTextContent('"id":"completed-cycle"')
  })

  it("loads summary only as fallback, preserving the stale contract and recovery context", async () => {
    apiMock.getLiveRefreshSnapshot.mockResolvedValue({ ok: false, snapshot: null, data_state: "stale" })
    apiMock.getLiveRefreshSummary.mockResolvedValue({ ...fresh, data_state: "stale", db_unavailable: true })
    const { client } = mount()
    await advance(20)
    await advance(20_000)
    expect(apiMock.getLiveRefreshSummary).toHaveBeenCalledTimes(1)
    expect(screen.getByTestId("snapshot")).toHaveTextContent('"authoritative":null')
    expect(screen.getByTestId("snapshot")).toHaveTextContent('"state":"stale"')
    apiMock.getLiveRefreshSnapshot.mockResolvedValue(fresh)
    await act(async () => { await client.invalidateQueries({ queryKey: ["live-refresh-snapshot"] }) })
    await advance()
    expect(screen.getByTestId("snapshot")).toHaveTextContent('"authoritative":"current"')
    expect(screen.getByTestId("snapshot")).toHaveTextContent('"dbUnavailable":false')
  })

  it("retains the last good board if both contract and fallback become unavailable", async () => {
    const { client } = mount()
    await advance()
    apiMock.getLiveRefreshSnapshot.mockResolvedValue({ ok: false, snapshot: null, data_state: "missing" })
    apiMock.getLiveRefreshSummary.mockResolvedValue({ ok: false, snapshot: null, data_state: "missing" })
    await act(async () => { await client.invalidateQueries({ queryKey: ["live-refresh-snapshot"] }) })
    await advance(20)
    expect(screen.getByTestId("snapshot")).toHaveTextContent('"id":"current"')
    expect(screen.getByTestId("snapshot")).toHaveTextContent('"authoritative":null')
    expect(screen.getByTestId("snapshot")).toHaveTextContent('"state":"missing"')
  })

  it("does not rewrite the large browser caches when only envelope age changes", async () => {
    const { client } = mount()
    await advance()
    apiMock.getLiveRefreshSnapshot.mockResolvedValue({ ...fresh, age_seconds: 20, snapshot: structuredClone(fresh.snapshot) })
    await act(async () => { await client.invalidateQueries({ queryKey: ["live-refresh-snapshot"] }) })
    await advance()
    expect(cacheMock.write).toHaveBeenCalledTimes(1)
    expect(cacheMock.writeIdb).toHaveBeenCalledTimes(1)
  })

  it("suspends hidden-page requests and catches up when visible again", async () => {
    await visibility(true)
    mount()
    await advance(30_000)
    expect(apiMock.getLiveRefreshSnapshot).not.toHaveBeenCalled()
    expect(apiMock.getLiveRefreshStatus).not.toHaveBeenCalled()
    await visibility(false)
    expect(apiMock.getLiveRefreshSnapshot).toHaveBeenCalledTimes(1)
    expect(apiMock.getLiveRefreshStatus).toHaveBeenCalledTimes(1)
    await visibility(true)
    await advance(60_000)
    expect(apiMock.getLiveRefreshSnapshot).toHaveBeenCalledTimes(1)
    await visibility(false)
    expect(apiMock.getLiveRefreshSnapshot).toHaveBeenCalledTimes(2)
    expect(apiMock.getLiveRefreshStatus).toHaveBeenCalledTimes(2)
  })
})
