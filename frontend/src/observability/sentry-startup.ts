/** Load optional error reporting before rendering without making SDK delivery an app dependency. */
export async function prepareErrorReporting(): Promise<void> {
  if (!import.meta.env.VITE_SENTRY_DSN) return

  try {
    const { initSentry } = await import("@/observability/sentry")
    initSentry()
  } catch (error) {
    console.error("Error reporting could not initialize", error)
  }
}
