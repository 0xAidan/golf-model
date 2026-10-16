/** Optional reporting loads independently of the app's initial render. */
export async function prepareErrorReporting(): Promise<void> {
  if (!import.meta.env.VITE_SENTRY_DSN) return

  try {
    const { initSentry } = await import("@/observability/sentry")
    initSentry()
  } catch (error) {
    console.error("Error reporting could not initialize", error)
  }
}

export function startErrorReportingAfterPaint(): void {
  if (!import.meta.env.VITE_SENTRY_DSN) return
  // The timer runs after the first animation-frame callback so the browser gets
  // a paint opportunity before downloading/initializing optional reporting.
  window.requestAnimationFrame(() => {
    window.setTimeout(() => { void prepareErrorReporting() }, 0)
  })
}
