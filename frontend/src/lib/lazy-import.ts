import { lazy, type ComponentType, type LazyExoticComponent } from "react"

const CHUNK_FAILURE_RE =
  /failed to fetch dynamically imported module|loading chunk|importing a module script failed/i

export const isChunkLoadError = (error: unknown): boolean => {
  if (!(error instanceof Error)) return false
  return CHUNK_FAILURE_RE.test(error.message)
}

type ReloadStorage = Pick<Storage, "getItem" | "setItem"> | Map<string, string>

type ChunkRecoveryOptions = {
  error: unknown
  release: string
  storage?: ReloadStorage
  reload?: () => void
}

const getStoredValue = (storage: ReloadStorage, key: string): string | null =>
  storage instanceof Map ? storage.get(key) ?? null : storage.getItem(key)

const setStoredValue = (storage: ReloadStorage, key: string, value: string): void => {
  if (storage instanceof Map) {
    storage.set(key, value)
    return
  }
  storage.setItem(key, value)
}

export const getCurrentRelease = (): string => import.meta.env.VITE_APP_RELEASE || "unknown"

/**
 * Refresh once for a newly deployed release. A second failure keeps the shell available.
 */
export const shouldHardReloadForChunkError = ({
  error,
  release,
  storage = window.sessionStorage,
  reload = () => window.location.reload(),
}: ChunkRecoveryOptions): boolean => {
  if (!isChunkLoadError(error)) return false

  const reloadKey = `golf-model.chunk-reload.${release}`
  if (getStoredValue(storage, reloadKey) != null) return false

  setStoredValue(storage, reloadKey, "1")
  reload()
  return true
}

export const lazyWithRetry = <T extends ComponentType<any>>(
  factory: () => Promise<{ default: T }>,
): LazyExoticComponent<T> => lazy(factory)
