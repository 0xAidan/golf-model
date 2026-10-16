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
    // Shared cards live in the fragment. They must never enter telemetry.
    url.hash = ""
    for (const [key] of url.searchParams) {
      if (SENSITIVE_QUERY_PARAMS.has(key.toLowerCase())) {
        url.searchParams.set(key, "[Filtered]")
      }
    }
    return url.toString()
  } catch {
    return value.split("#", 1)[0]
  }
}

function scrubFragments(value: unknown, seen = new WeakSet<object>()): unknown {
  if (typeof value === "string") return value.replace(/#[^\r\n]*/g, "#[Filtered]")
  if (!value || typeof value !== "object") return value
  if (seen.has(value)) return "[Circular]"
  seen.add(value)
  const result = Array.isArray(value)
    ? value.map(item => scrubFragments(item, seen))
    : Object.fromEntries(Object.entries(value).map(([key, item]) => [
      key,
      ["url", "from", "to"].includes(key) && typeof item === "string"
        ? scrubUrl(item)
        : scrubFragments(item, seen),
    ]))
  seen.delete(value)
  return result
}

export const scrubSentryBreadcrumb = (breadcrumb: Sentry.Breadcrumb): Sentry.Breadcrumb =>
  scrubFragments(breadcrumb) as Sentry.Breadcrumb

export const scrubSentryEvent = <T extends Sentry.Event>(event: T): T => {
  // Apply even when request is absent: navigation breadcrumbs, tags, spans and
  // console arguments can also contain the current URL or its fragment.
  event = scrubFragments(event) as T
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
    beforeSendTransaction: scrubSentryEvent,
    beforeBreadcrumb: scrubSentryBreadcrumb,
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
