import { describe, expect, test } from "vitest"

import {
  createLastGoodBoardStore,
  type CachedOperatorBoard,
} from "@/features/operator-data/last-good-store"
import type { OperatorBoard } from "@/features/operator-data/operator-api"

const board = {
  schema_version: "operator-read-model/v1",
  track: "champion" as const,
  mode: "live" as const,
  state: "fresh",
  reason: { code: "ok", message: "Ready" },
  event: { event_id: "event-1" },
  source: { snapshot_id: "snapshot-1" },
  eligibility: {},
  rankings: [],
  leaderboard: [],
  picks: { matchups: [], value_bets: [] },
} satisfies OperatorBoard

describe("last-good board store", () => {
  test("returns only an identity-matching newest board", async () => {
    const store = createLastGoodBoardStore({ maxEntries: 2, release: "test" })
    const first: CachedOperatorBoard = {
      identity: {
        schemaVersion: "operator-read-model/v1",
        release: "test",
        track: "champion",
        mode: "live",
        eventId: "event-1",
      },
      board: { ...board, source: { snapshot_id: "snapshot-1" } },
      savedAt: 1,
      snapshotId: "snapshot-1",
    }
    const newest = { ...first, savedAt: 2, snapshotId: "snapshot-2", board: { ...board, source: { snapshot_id: "snapshot-2" } } }

    await store.save(first)
    await store.save(newest)

    await expect(store.read(first.identity)).resolves.toEqual(newest)
    await expect(
      store.read({ ...first.identity, track: "challenger" }),
    ).resolves.toBeNull()
  })

  test("does not persist boards whose identity does not match their payload", async () => {
    const store = createLastGoodBoardStore({ maxEntries: 2, release: "test" })
    const cached: CachedOperatorBoard = {
      identity: {
        schemaVersion: "operator-read-model/v1",
        release: "test",
        track: "challenger",
        mode: "live",
        eventId: "event-1",
      },
      board,
      savedAt: 1,
      snapshotId: "snapshot-1",
    }

    await store.save(cached)

    await expect(store.read(cached.identity)).resolves.toBeNull()
  })
})
