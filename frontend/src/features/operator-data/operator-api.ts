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

const GET_RETRY_ATTEMPTS = 2
const GET_RETRY_BASE_MS = 250
const REQUEST_TIMEOUT_MS = 20_000
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

const waitForRetry = (delayMs: number, signal?: AbortSignal): Promise<void> =>
  new Promise((resolve, reject) => {
    const timer = window.setTimeout(resolve, delayMs)
    signal?.addEventListener(
      "abort",
      () => {
        window.clearTimeout(timer)
        reject(signal.reason ?? new DOMException("Request aborted", "AbortError"))
      },
      { once: true },
    )
  })

const isRetryableGetError = (error: unknown): boolean =>
  error instanceof ApiError ? error.status === 429 || error.status >= 500 : !(error instanceof DOMException)

const requestGet = async <T>(path: string, signal?: AbortSignal): Promise<T> => {
  for (let attempt = 0; attempt <= GET_RETRY_ATTEMPTS; attempt += 1) {
    const controller = signal ? null : new AbortController()
    const timeout = controller ? window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS) : null
    try {
      const response = await fetch(path, { method: "GET", signal: signal ?? controller?.signal })
      if (!response.ok) throw await createApiError(response)
      return (await response.json()) as T
    } catch (error) {
      const timeoutError =
        controller?.signal.aborted && !signal?.aborted
          ? new ApiError({
              message: `Request timed out after ${REQUEST_TIMEOUT_MS / 1_000}s`,
              status: 0,
              code: "timeout",
              isTimeout: true,
            })
          : error
      if (attempt === GET_RETRY_ATTEMPTS || !isRetryableGetError(timeoutError)) throw timeoutError
      const retryAfter = timeoutError instanceof ApiError ? timeoutError.retryAfterMs : null
      await waitForRetry(Math.min(retryAfter ?? GET_RETRY_BASE_MS * 2 ** attempt, MAX_RETRY_AFTER_MS), signal)
    } finally {
      if (timeout !== null) window.clearTimeout(timeout)
    }
  }
  throw new Error("Unreachable GET retry state")
}

export const getOperatorBootstrap = (signal?: AbortSignal): Promise<OperatorBootstrap> =>
  requestGet<OperatorBootstrap>("/api/operator/bootstrap", signal)

export const getOperatorBoard = (
  { track, mode, eventId }: { track: OperatorTrack; mode: OperatorMode; eventId?: string | null },
  signal?: AbortSignal,
): Promise<OperatorBoard> => {
  const params = new URLSearchParams({ track, mode })
  if (eventId) params.set("event_id", eventId)
  return requestGet<OperatorBoard>(`/api/operator/board?${params.toString()}`, signal)
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
