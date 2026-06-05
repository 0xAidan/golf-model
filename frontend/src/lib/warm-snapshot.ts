import type { LiveRefreshSnapshot, LiveRefreshSnapshotResponse } from "@/lib/types"

export const WARM_SNAPSHOT_STORAGE_KEY = "golf-model.warm-snapshot"

export function readWarmSnapshotEnvelope(): LiveRefreshSnapshotResponse | null {
  if (typeof sessionStorage === "undefined") return null
  try {
    const raw = sessionStorage.getItem(WARM_SNAPSHOT_STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as LiveRefreshSnapshotResponse
    if (!parsed || typeof parsed !== "object") return null
    return parsed
  } catch {
    return null
  }
}

export function writeWarmSnapshotEnvelope(envelope: LiveRefreshSnapshotResponse): void {
  if (typeof sessionStorage === "undefined") return
  try {
    sessionStorage.setItem(WARM_SNAPSHOT_STORAGE_KEY, JSON.stringify(envelope))
  } catch {
    // Quota or private mode — ignore.
  }
}

export function readWarmSnapshot(): LiveRefreshSnapshot | null {
  return readWarmSnapshotEnvelope()?.snapshot ?? null
}
