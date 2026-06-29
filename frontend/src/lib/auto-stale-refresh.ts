export const AUTO_STALE_REFRESH_STORAGE_KEY = "golf-auto-refresh-at"
export const AUTO_STALE_REFRESH_COOLDOWN_MS = 10 * 60 * 1000

export const shouldAutoStaleRefresh = (now = Date.now()): boolean => {
  if (typeof sessionStorage === "undefined") return true
  try {
    const last = Number(sessionStorage.getItem(AUTO_STALE_REFRESH_STORAGE_KEY) ?? "0")
    if (!Number.isFinite(last) || last <= 0) return true
    return now - last >= AUTO_STALE_REFRESH_COOLDOWN_MS
  } catch {
    return true
  }
}

export const markAutoStaleRefresh = (now = Date.now()): void => {
  if (typeof sessionStorage === "undefined") return
  try {
    sessionStorage.setItem(AUTO_STALE_REFRESH_STORAGE_KEY, String(now))
  } catch {
    // Quota or private mode — ignore.
  }
}
