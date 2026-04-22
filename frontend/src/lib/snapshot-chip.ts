export type SnapshotChipTone = "green" | "amber" | "red" | "grey"

export const GREEN_MAX_SECONDS = 30 * 60
export const AMBER_MAX_SECONDS = 60 * 60

export function computeAgeSeconds(
  generatedAt: string | null | undefined,
  nowMs: number,
): number | null {
  if (!generatedAt) return null
  const ts = Date.parse(generatedAt)
  if (Number.isNaN(ts)) return null
  return Math.max(0, Math.floor((nowMs - ts) / 1000))
}

export function formatAgeLabel(ageSeconds: number | null): string {
  if (ageSeconds === null) return "—"
  if (ageSeconds > AMBER_MAX_SECONDS) return "stale (>60m)"
  if (ageSeconds < 60) return `${ageSeconds}s ago`
  const minutes = Math.floor(ageSeconds / 60)
  return `${minutes}m ago`
}

export function resolveTone(ageSeconds: number | null): SnapshotChipTone {
  if (ageSeconds === null) return "grey"
  if (ageSeconds > AMBER_MAX_SECONDS) return "red"
  if (ageSeconds >= GREEN_MAX_SECONDS) return "amber"
  return "green"
}

export function normalizeSourceLabel(source: string | null | undefined): string {
  const value = (source ?? "").trim().toLowerCase()
  if (value === "live" || value === "replay" || value === "fixture") {
    return value.toUpperCase()
  }
  return "—"
}
