import type { LiveRefreshSnapshot, LiveRefreshSnapshotResponse } from "@/lib/types"

export const WARM_SNAPSHOT_STORAGE_KEY = "golf-model.warm-snapshot"

const DEFAULT_STALE_AFTER_SECONDS = 3900

const envelopeIsTooStale = (
  envelope: LiveRefreshSnapshotResponse,
  staleAfterSeconds: number,
): boolean => {
  if (
    envelope.age_seconds != null &&
    envelope.stale_after_seconds != null &&
    envelope.age_seconds > envelope.stale_after_seconds
  ) {
    return true
  }
  if (envelope.age_seconds != null && envelope.age_seconds > staleAfterSeconds) {
    return true
  }
  const generatedAt = envelope.generated_at ?? envelope.snapshot?.generated_at
  if (!generatedAt) return false
  try {
    const generatedMs = Date.parse(generatedAt)
    if (!Number.isFinite(generatedMs)) return false
    return Date.now() - generatedMs > staleAfterSeconds * 1000
  } catch {
    return false
  }
}

export function readWarmSnapshotEnvelope(
  staleAfterSeconds = DEFAULT_STALE_AFTER_SECONDS,
): LiveRefreshSnapshotResponse | null {
  if (typeof sessionStorage === "undefined") return null
  try {
    const raw = sessionStorage.getItem(WARM_SNAPSHOT_STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as LiveRefreshSnapshotResponse
    if (!parsed || typeof parsed !== "object") return null
    if (envelopeIsTooStale(parsed, staleAfterSeconds)) return null
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

export function readWarmSnapshot(staleAfterSeconds?: number): LiveRefreshSnapshot | null {
  return readWarmSnapshotEnvelope(staleAfterSeconds)?.snapshot ?? null
}
