import { Component, type ErrorInfo, type ReactNode } from "react"

import { ErrorState } from "@/components/ui/feedback-state"
import { isChunkLoadError } from "@/lib/lazy-import"

type RouteErrorBoundaryProps = {
  children: ReactNode
  resetKey?: string
}

type RouteErrorBoundaryState = {
  hasError: boolean
  error: Error | null
  errorInfo: ErrorInfo | null
}

export class RouteErrorBoundary extends Component<
  RouteErrorBoundaryProps,
  RouteErrorBoundaryState
> {
  public constructor(props: RouteErrorBoundaryProps) {
    super(props)
    this.state = { hasError: false, error: null, errorInfo: null }
  }

  public static getDerivedStateFromError(error: Error): Partial<RouteErrorBoundaryState> {
    return { hasError: true, error }
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    this.setState({ errorInfo })
    console.error("Route render error", error, errorInfo)
  }

  public componentDidUpdate(prevProps: RouteErrorBoundaryProps): void {
    if (this.state.hasError && prevProps.resetKey !== this.props.resetKey) {
      this.setState({ hasError: false, error: null, errorInfo: null })
    }
  }

  private handleRetry = (): void => {
    this.setState({ hasError: false, error: null, errorInfo: null })
  }

  private handleReload = (): void => {
    window.location.reload()
  }

  public render(): ReactNode {
    if (!this.state.hasError) {
      return this.props.children
    }

    const { error, errorInfo } = this.state
    const chunkFailure = error != null && isChunkLoadError(error)
    const message = chunkFailure
      ? "This page failed to load after an app update. Retry or reload to fetch the latest bundle."
      : "Route failed to render. Retry or refresh and try again."

    return (
      <div
        className="route-error-boundary"
        role="alert"
        data-testid="route-error-boundary"
        data-chunk-failure={chunkFailure ? "true" : "false"}
      >
        <ErrorState
          message={message}
          onRetry={this.handleRetry}
        />
        {chunkFailure ? (
          <button
            type="button"
            className="btn btn-primary btn-compact route-error-boundary-reload"
            onClick={this.handleReload}
            data-testid="route-error-reload"
          >
            Reload page
          </button>
        ) : null}
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
