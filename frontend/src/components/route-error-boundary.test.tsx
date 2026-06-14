import { render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"

import { RouteErrorBoundary } from "@/components/route-error-boundary"

function ThrowingPage({ message }: { message: string }): never {
  throw new Error(message)
}

describe("RouteErrorBoundary", () => {
  it("shows dev error details when a child throws", () => {
    vi.stubEnv("DEV", true)
    render(
      <MemoryRouter>
        <RouteErrorBoundary>
          <ThrowingPage message="Test route crash" />
        </RouteErrorBoundary>
      </MemoryRouter>,
    )

    expect(screen.getByTestId("route-error-boundary")).toBeInTheDocument()
    expect(screen.getByTestId("error-state")).toHaveTextContent(/route failed to render/i)
    expect(screen.getByTestId("route-error-dev-details")).toHaveTextContent("Test route crash")
    vi.unstubAllEnvs()
  })

  it("detects chunk load failures and offers reload", () => {
    render(
      <MemoryRouter>
        <RouteErrorBoundary>
          <ThrowingPage message="Failed to fetch dynamically imported module" />
        </RouteErrorBoundary>
      </MemoryRouter>,
    )

    expect(screen.getByTestId("route-error-boundary")).toHaveAttribute("data-chunk-failure", "true")
    expect(screen.getByTestId("route-error-reload")).toBeInTheDocument()
  })

  it("resets when resetKey changes", () => {
    const { rerender } = render(
      <MemoryRouter>
        <RouteErrorBoundary resetKey="a">
          <ThrowingPage message="Broken" />
        </RouteErrorBoundary>
      </MemoryRouter>,
    )

    expect(screen.getByTestId("route-error-boundary")).toBeInTheDocument()

    rerender(
      <MemoryRouter>
        <RouteErrorBoundary resetKey="b">
          <div data-testid="ok-page">OK</div>
        </RouteErrorBoundary>
      </MemoryRouter>,
    )

    expect(screen.getByTestId("ok-page")).toBeInTheDocument()
  })
})
