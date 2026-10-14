import { describe, expect, it } from "vitest"

import type { LiveRefreshSnapshotResponse } from "@/lib/types"
import { refreshIsActive, snapshotPollInterval, statusPollInterval } from "./live-snapshot-polling"

const fresh: LiveRefreshSnapshotResponse = {
  ok: true,
  data_state: "fresh",
  snapshot: { snapshot_id: "current" },
  age_seconds: 30,
  stale_after_seconds: 3720,
}

describe("legacy polling policy", () => {
  it("does not mistake an idle, running worker for an active refresh", () => {
    const status = { status: { running: true, worker_running: true, refresh_state: "idle" } }
    expect(refreshIsActive(status, false)).toBe(false)
    expect(statusPollInterval(status, false, false)).toBe(15_000)
  })

  it.each(["queued", "running", "busy", "refreshing"])("tracks %s refresh progress quickly", state => {
    expect(statusPollInterval({ status: { progress: { refresh_state: state } } }, false, false)).toBe(2_500)
  })

  it("keeps manual refresh fast before server status catches up", () => {
    expect(statusPollInterval(undefined, true, false)).toBe(2_500)
    expect(snapshotPollInterval({ envelope: fresh, updatedAt: 1_000, now: 1_000, refreshing: true, hidden: false })).toBe(10_000)
  })

  it("slows idle upcoming snapshots but preserves live-round cadence", () => {
    expect(snapshotPollInterval({ envelope: fresh, updatedAt: 1_000, now: 1_000, refreshing: false, hidden: false })).toBe(60_000)
    const live = { ...fresh, snapshot: { live_tournament: { active: true } } }
    expect(snapshotPollInterval({ envelope: live, updatedAt: 1_000, now: 1_000, refreshing: false, hidden: false })).toBe(10_000)
  })

  it("rechecks readiness at its freshness deadline without using the client clock as the source age", () => {
    const nearlyStale = { ...fresh, age_seconds: 3717 }
    expect(snapshotPollInterval({ envelope: nearlyStale, updatedAt: 1_000, now: 2_000, refreshing: false, hidden: false })).toBe(3_000)
    expect(snapshotPollInterval({ envelope: nearlyStale, updatedAt: 1_000, now: 9_000, refreshing: false, hidden: false })).toBe(1_000)
  })

  it("does not repeatedly request an already stale or unavailable snapshot", () => {
    expect(snapshotPollInterval({ envelope: { ...fresh, ok: false, data_state: "stale", snapshot: null }, updatedAt: 1_000, now: 999_999, refreshing: false, hidden: false })).toBe(60_000)
  })

  it("suspends all intervals while the tab is hidden", () => {
    expect(statusPollInterval(undefined, true, true)).toBe(false)
    expect(snapshotPollInterval({ envelope: fresh, updatedAt: 1_000, refreshing: true, hidden: true })).toBe(false)
  })
})
