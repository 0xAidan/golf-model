export type OperatorTrack = "champion" | "challenger"
export type OperatorMode = "live" | "upcoming" | "past"
export type OperatorDataState = "fresh" | "refreshing" | "stale" | "empty" | "unavailable" | "error"

export type OperatorReason = {
  code: string
  message: string
}

export type OperatorSource = {
  snapshot_id?: string | null
  generated_at?: string | null
  age_seconds?: number | null
  stale_after_seconds?: number | null
  section?: string
}

export type OperatorEvent = {
  event_id?: string | null
  event_name?: string | null
  course_name?: string | null
}

export type OperatorBoard = {
  schema_version: string
  track: OperatorTrack
  mode: OperatorMode
  state: OperatorDataState
  reason: OperatorReason
  event: OperatorEvent
  source: OperatorSource
  eligibility: Record<string, unknown>
  rankings: Array<Record<string, unknown>>
  leaderboard: Array<Record<string, unknown>>
  picks: {
    matchups: Array<Record<string, unknown>>
    value_bets: Array<Record<string, unknown>>
  }
}

export type OperatorBootstrapSection = {
  available: boolean
  event_id: string | null
  event_name: string | null
  state: OperatorDataState
  reason: OperatorReason
}

export type OperatorBootstrap = {
  schema_version: string
  state: OperatorDataState
  reason: OperatorReason
  source: OperatorSource
  tracks: Record<OperatorTrack, Record<OperatorMode, OperatorBootstrapSection>>
}

type ApiErrorPayload = {
  detail?: {
    code?: string
    message?: string
    request_id?: string
  } | string
  code?: string
  message?: string
  request_id?: string
}

export class ApiError extends Error {
  status: number
  code: string | null
  requestId: string | null
  isTimeout: boolean
  retryAfterMs: number | null

  constructor({
    message,
    status,
    code = null,
    requestId = null,
    isTimeout = false,
    retryAfterMs = null,
  }: {
    message: string
    status: number
    code?: string | null
    requestId?: string | null
    isTimeout?: boolean
    retryAfterMs?: number | null
  }) {
    super(message)
    this.name = "ApiError"
    this.status = status
    this.code = code
    this.requestId = requestId
    this.isTimeout = isTimeout
    this.retryAfterMs = retryAfterMs
  }
}

const GET_RETRY_ATTEMPTS = 1
const GET_RETRY_BASE_MS = 250
const REQUEST_TIMEOUT_MS = 10_000
const MAX_RETRY_AFTER_MS = 1_000

const parseRetryAfterMs = (header: string | null): number | null => {
  if (!header) return null
  const seconds = Number(header)
  if (Number.isFinite(seconds) && seconds >= 0) return seconds * 1_000
  const dateMs = Date.parse(header)
  return Number.isFinite(dateMs) ? Math.max(0, dateMs - Date.now()) : null
}

const parsePayload = async (response: Response): Promise<ApiErrorPayload> => {
  const text = await response.text()
  if (!text) return {}
  try {
    return JSON.parse(text) as ApiErrorPayload
  } catch {
    return { message: text }
  }
}

const createApiError = async (response: Response): Promise<ApiError> => {
  const payload = await parsePayload(response)
  const detail = typeof payload.detail === "object" && payload.detail ? payload.detail : {}
  const detailText = typeof payload.detail === "string" ? payload.detail : null
  return new ApiError({
    message: detail.message ?? payload.message ?? detailText ?? `Request failed: ${response.status}`,
    status: response.status,
    code: detail.code ?? payload.code ?? null,
    requestId: detail.request_id ?? payload.request_id ?? response.headers.get("x-request-id"),
    retryAfterMs: parseRetryAfterMs(response.headers.get("retry-after")),
  })
}

const waitForRetry = (delayMs: number, signal: AbortSignal): Promise<void> =>
  new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(signal.reason)
      return
    }
    const cleanup = () => signal.removeEventListener("abort", abort)
    const timer = window.setTimeout(() => { cleanup(); resolve() }, delayMs)
    const abort = () => {
      window.clearTimeout(timer)
      cleanup()
      reject(signal.reason)
    }
    signal.addEventListener("abort", abort, { once: true })
  })

const isRetryableGetError = (error: unknown): boolean =>
  error instanceof ApiError ? error.status === 429 || error.status >= 500 : error instanceof TypeError

/** Read-only JSON with one retry owner and one deadline, including body/backoff time.
 * TanStack consumers should pass their signal and set retry: false.
 */
export const getReadOnlyJson = async <T>(path: string, signal?: AbortSignal): Promise<T> => {
  const controller = new AbortController()
  const abortFromCaller = () => controller.abort(signal?.reason ?? new DOMException("Request aborted", "AbortError"))
  if (signal?.aborted) {
    abortFromCaller()
    throw controller.signal.reason
  }
  signal?.addEventListener("abort", abortFromCaller, { once: true })
  const timeout = window.setTimeout(() => controller.abort(new ApiError({
    message: `Request timed out after ${REQUEST_TIMEOUT_MS / 1_000}s`,
    status: 0,
    code: "timeout",
    isTimeout: true,
  })), REQUEST_TIMEOUT_MS)

  try {
    for (let attempt = 0; attempt <= GET_RETRY_ATTEMPTS; attempt += 1) {
      try {
        if (controller.signal.aborted) throw controller.signal.reason
        const response = await fetch(path, { method: "GET", signal: controller.signal })
        if (!response.ok) throw await createApiError(response)
        return (await response.json()) as T
      } catch (error) {
        if (controller.signal.aborted) throw controller.signal.reason
        if (attempt === GET_RETRY_ATTEMPTS || !isRetryableGetError(error)) throw error
        const retryAfter = error instanceof ApiError ? error.retryAfterMs : null
        await waitForRetry(Math.min(retryAfter ?? GET_RETRY_BASE_MS, MAX_RETRY_AFTER_MS), controller.signal)
      }
    }
    throw new Error("Unreachable GET retry state")
  } finally {
    window.clearTimeout(timeout)
    signal?.removeEventListener("abort", abortFromCaller)
  }
}

export const getOperatorBootstrap = (signal?: AbortSignal): Promise<OperatorBootstrap> =>
  getReadOnlyJson<OperatorBootstrap>("/api/operator/bootstrap", signal)

/** Isolated, read-only snapshot service used by the matchup desk. */
export const getDeskBoard = (
  { track, mode }: { track: OperatorTrack; mode: Exclude<OperatorMode, "past"> },
  signal?: AbortSignal,
): Promise<OperatorBoard> =>
  getReadOnlyJson<OperatorBoard>(`/api/desk/board?${new URLSearchParams({ track, mode })}`, signal)

export const getOperatorBoard = (
  { track, mode, eventId }: { track: OperatorTrack; mode: OperatorMode; eventId?: string | null },
  signal?: AbortSignal,
): Promise<OperatorBoard> => {
  const params = new URLSearchParams({ track, mode })
  if (eventId) params.set("event_id", eventId)
  return getReadOnlyJson<OperatorBoard>(`/api/operator/board?${params.toString()}`, signal)
}

/** Manual-only worker wake-up. Mutations deliberately do not retry. */
export const requestRefreshNow = async (): Promise<void> => {
  const response = await fetch("/api/live-refresh/refresh", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  })
  if (!response.ok && response.status !== 202) throw await createApiError(response)
}
