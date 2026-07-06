import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { StatusBanner, StatusBannerStack } from "@/components/ui/status-banner"

describe("StatusBanner", () => {
  it("renders title and message with tone", () => {
    render(
      <StatusBanner tone="danger" title="Worker down" message="The background worker stopped updating." />,
    )
    expect(screen.getByTestId("status-banner")).toHaveAttribute("data-tone", "danger")
    expect(screen.getByText("Worker down")).toBeInTheDocument()
    expect(screen.getByText(/background worker stopped/i)).toBeInTheDocument()
  })

  it("fires optional action", async () => {
    const user = userEvent.setup()
    const onClick = vi.fn()
    render(
      <StatusBanner
        tone="warn"
        title="Stale data"
        message="Snapshot is old."
        action={{ label: "Refresh", onClick }}
      />,
    )
    await user.click(screen.getByRole("button", { name: "Refresh" }))
    expect(onClick).toHaveBeenCalledOnce()
  })
})

describe("StatusBannerStack", () => {
  it("shows highest severity first and collapses overflow", () => {
    render(
      <StatusBannerStack
        banners={[
          { id: "info", tone: "info", title: "Info", message: "Minor" },
          { id: "danger", tone: "danger", title: "Critical", message: "Major" },
        ]}
      />,
    )
    expect(screen.getByText("Critical")).toBeInTheDocument()
    expect(screen.getByText("+ 1 more")).toBeInTheDocument()
  })
})
