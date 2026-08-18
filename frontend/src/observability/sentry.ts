import * as Sentry from "@sentry/react"

type RouteErrorContext = {
  route: string
  track?: string | null
  mode?: string | null
  snapshotId?: string | null
}

const SENSITIVE_HEADERS = new Set(["authorization", "api-key", "x-api-key", "x-auth-token"])
const SENSITIVE_QUERY_PARAMS = new Set(["api_key", "apikey", "auth", "authorization", "password", "secret", "token"])

export const getRelease = (): string => import.meta.env.VITE_APP_RELEASE || "unknown"

const scrubUrl = (value: string): string => {
  try {
    const url = new URL(value, window.location.origin)
    for (const [key] of url.searchParams) {
      if (SENSITIVE_QUERY_PARAMS.has(key.toLowerCase())) {
        url.searchParams.set(key, "[Filtered]")
      }
    }
    return url.toString()
  } catch {
    return value
  }
}

export const scrubSentryEvent = (event: Sentry.ErrorEvent): Sentry.ErrorEvent => {
  if (!event.request) return event

  if (event.request.headers) {
    event.request.headers = Object.fromEntries(
      Object.entries(event.request.headers).filter(([key]) => !SENSITIVE_HEADERS.has(key.toLowerCase())),
    )
  }
  if (event.request.data != null) {
    event.request.data = "[Filtered]"
  }
  if (event.request.url) {
    event.request.url = scrubUrl(event.request.url)
  }
  return event
}

export const initSentry = (): void => {
  const dsn = import.meta.env.VITE_SENTRY_DSN
  if (!dsn) return

  Sentry.init({
    dsn,
    environment: import.meta.env.VITE_SENTRY_ENVIRONMENT || import.meta.env.MODE,
    release: getRelease(),
    tracesSampleRate: 0.1,
    beforeSend: scrubSentryEvent,
    sendDefaultPii: false,
  })
}

export const captureRouteException = (error: unknown, context: RouteErrorContext): string => {
  return Sentry.captureException(error, {
    tags: {
      route: context.route,
      track: context.track ?? "unknown",
      mode: context.mode ?? "unknown",
      snapshot_id: context.snapshotId ?? "unknown",
      release: getRelease(),
    },
  })
}
