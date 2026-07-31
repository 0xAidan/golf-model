import { Component, type ErrorInfo, type ReactNode } from "react"

import { ErrorState } from "@/components/ui/feedback-state"
import { isChunkLoadError, shouldHardReloadForChunkError } from "@/lib/lazy-import"
import { captureRouteException } from "@/observability/sentry"

type RouteErrorBoundaryProps = {
  children: ReactNode
  resetKey?: string
  route?: string
  track?: string | null
  mode?: string | null
  snapshotId?: string | null
}

type RouteErrorBoundaryState = {
  hasError: boolean
  error: Error | null
  errorInfo: ErrorInfo | null
  eventId: string | null
}

export class RouteErrorBoundary extends Component<
  RouteErrorBoundaryProps,
  RouteErrorBoundaryState
> {
  public constructor(props: RouteErrorBoundaryProps) {
    super(props)
    this.state = { hasError: false, error: null, errorInfo: null, eventId: null }
  }

  public static getDerivedStateFromError(error: Error): Partial<RouteErrorBoundaryState> {
    return { hasError: true, error }
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    const eventId = captureRouteException(error, {
      route: this.props.route ?? "unknown",
      track: this.props.track,
      mode: this.props.mode,
      snapshotId: this.props.snapshotId,
    })
    this.setState({ errorInfo, eventId })
    shouldHardReloadForChunkError({ error, release: import.meta.env.VITE_APP_RELEASE || "unknown" })
    console.error("Route render error", error, errorInfo)
  }

  public componentDidUpdate(prevProps: RouteErrorBoundaryProps): void {
    if (this.state.hasError && prevProps.resetKey !== this.props.resetKey) {
      this.setState({ hasError: false, error: null, errorInfo: null, eventId: null })
    }
  }

  private handleRetry = (): void => {
    this.setState({ hasError: false, error: null, errorInfo: null, eventId: null })
  }

  public render(): ReactNode {
    if (!this.state.hasError) {
      return this.props.children
    }

    const { error, errorInfo, eventId } = this.state
    const chunkFailure = error != null && isChunkLoadError(error)

    return (
      <div
        className="route-error-boundary"
        role="alert"
        data-testid="route-error-boundary"
        data-chunk-failure={chunkFailure ? "true" : "false"}
      >
        {chunkFailure ? (
          <p className="text-sm text-muted-foreground">
            This view is unavailable after an app update. Navigation remains available; refresh later if it persists.
          </p>
        ) : (
          <ErrorState message="Route failed to render. Retry or refresh and try again." onRetry={this.handleRetry} />
        )}
        {eventId ? <p className="text-xs text-muted-foreground">Recovery event: {eventId}</p> : null}
        {import.meta.env.DEV && error ? (
          <details className="route-error-boundary-dev" data-testid="route-error-dev-details">
            <summary>Developer error details</summary>
            <pre className="route-error-boundary-message">{error.message}</pre>
            {errorInfo?.componentStack ? (
              <pre className="route-error-boundary-stack">{errorInfo.componentStack}</pre>
            ) : null}
          </details>
        ) : null}
      </div>
    )
  }
}
