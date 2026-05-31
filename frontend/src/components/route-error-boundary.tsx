import { Component, type ErrorInfo, type ReactNode } from "react"

type RouteErrorBoundaryProps = {
  children: ReactNode
}

type RouteErrorBoundaryState = {
  hasError: boolean
}

export class RouteErrorBoundary extends Component<
  RouteErrorBoundaryProps,
  RouteErrorBoundaryState
> {
  public constructor(props: RouteErrorBoundaryProps) {
    super(props)
    this.state = { hasError: false }
  }

  public static getDerivedStateFromError(): RouteErrorBoundaryState {
    return { hasError: true }
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    // Keep route crashes visible in browser/devtools without crashing the full app shell.
    console.error("Route render error", error, errorInfo)
  }

  public render(): ReactNode {
    if (this.state.hasError) {
      return (
        <div
          role="alert"
          style={{
            flex: 1,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "var(--text)",
            fontFamily: "var(--font-mono)",
            fontSize: 12,
            padding: 16,
          }}
        >
          Route failed to render. Refresh and try again.
        </div>
      )
    }
    return this.props.children
  }
}
