import { lazy, type ComponentType, type LazyExoticComponent } from "react"

const CHUNK_FAILURE_RE =
  /failed to fetch dynamically imported module|loading chunk|importing a module script failed/i

export const isChunkLoadError = (error: unknown): boolean => {
  if (!(error instanceof Error)) return false
  return CHUNK_FAILURE_RE.test(error.message)
}

/**
 * Retry dynamic imports once after deploys that invalidate cached lazy chunks.
 */
export const lazyWithRetry = <T extends ComponentType<any>>(
  factory: () => Promise<{ default: T }>,
  retries = 1,
): LazyExoticComponent<T> =>
  lazy(async () => {
    let lastError: unknown
    for (let attempt = 0; attempt <= retries; attempt += 1) {
      try {
        return await factory()
      } catch (error) {
        lastError = error
        if (!isChunkLoadError(error) || attempt >= retries) break
        await new Promise((resolve) => window.setTimeout(resolve, 250))
      }
    }
    throw lastError
  })
