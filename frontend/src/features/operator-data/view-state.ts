import type { OperatorBoard, OperatorBootstrap } from "@/features/operator-data/operator-api"

export type PreviewViewState = "loading" | "ready" | "stale" | "empty" | "unavailable" | "error"

export const getPreviewViewState = ({
  bootstrap,
  board,
  hasLastGood,
  cacheHydrationPending,
  isBoardLoading,
  isBoardError,
}: {
  bootstrap: OperatorBootstrap | undefined
  board: OperatorBoard | undefined
  hasLastGood: boolean
  cacheHydrationPending: boolean
  isBoardLoading: boolean
  isBoardError: boolean
}): PreviewViewState => {
  if (cacheHydrationPending || (!bootstrap && !isBoardError)) return "loading"
  if (bootstrap?.state === "error") return hasLastGood ? "stale" : "error"
  if (bootstrap?.state === "unavailable") return hasLastGood ? "stale" : "unavailable"
  if (isBoardLoading && !board && !hasLastGood) return "loading"
  if (board?.state === "fresh" || board?.state === "refreshing") return "ready"
  if (board?.state === "empty") return hasLastGood ? "stale" : "empty"
  if (board?.state === "unavailable") return hasLastGood ? "stale" : "unavailable"
  if (board?.state === "stale") return "stale"
  if (isBoardError) return hasLastGood ? "stale" : "error"
  return hasLastGood ? "stale" : "unavailable"
}

export type OperatorPreferences = {
  version: 1
  book: string | null
  minEdge: number
  search: string
  columnsByRoute: Record<string, string[]>
}

const PREFERENCES_KEY = "golf-model.operator-preferences/v1"
const LEGACY_BOOK_KEY = "golf-model.selected-books"
const LEGACY_MIN_EDGE_KEY = "golf-model.min-edge"
const LEGACY_SEARCH_KEY = "golf-model.matchup-search"

const defaultPreferences = (): OperatorPreferences => ({
  version: 1,
  book: null,
  minEdge: 0.02,
  search: "",
  columnsByRoute: {},
})

const parseJson = <T>(value: string | null): T | null => {
  if (!value) return null
  try {
    return JSON.parse(value) as T
  } catch {
    return null
  }
}

export const loadOperatorPreferences = (storage: Storage = window.localStorage): OperatorPreferences => {
  const existing = parseJson<OperatorPreferences>(storage.getItem(PREFERENCES_KEY))
  if (existing?.version === 1) return existing

  const selectedBooks = parseJson<string[]>(storage.getItem(LEGACY_BOOK_KEY))
  const legacyMinEdge = parseJson<number>(storage.getItem(LEGACY_MIN_EDGE_KEY))
  const legacySearch = parseJson<string>(storage.getItem(LEGACY_SEARCH_KEY))
  const migrated: OperatorPreferences = {
    ...defaultPreferences(),
    book: selectedBooks?.[0] ?? null,
    minEdge: typeof legacyMinEdge === "number" ? legacyMinEdge : 0.02,
    search: typeof legacySearch === "string" ? legacySearch : "",
  }
  storage.setItem(PREFERENCES_KEY, JSON.stringify(migrated))
  return migrated
}

export const saveOperatorPreferences = (
  preferences: OperatorPreferences,
  storage: Storage = window.localStorage,
): void => {
  storage.setItem(PREFERENCES_KEY, JSON.stringify(preferences))
}
