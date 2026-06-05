import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { ReactNode } from "react"
import { describe, expect, it, vi, beforeEach } from "vitest"

import { MonitoringShell } from "@/components/monitoring/monitoring-shell"
import { wrapMonitoringTest } from "@/test/monitoring-test-utils"

vi.mock("@/hooks/use-media-query", () => ({
  useIsNarrowViewport: () => true,
}))

function renderShell(ui: ReactNode) {
  return render(wrapMonitoringTest(ui))
}

describe("MonitoringShell drawer keyboard", () => {
  beforeEach(() => {
    vi.stubGlobal("innerWidth", 375)
    window.dispatchEvent(new Event("resize"))
  })

  it("opens drawer with menu button and closes on Escape", async () => {
    const user = userEvent.setup()
    renderShell(
      <MonitoringShell headline="Test event">
        <div data-testid="main-content">Board</div>
      </MonitoringShell>,
    )

    const toggle = screen.getByTestId("mobile-menu-open")
    expect(toggle).toHaveAttribute("aria-expanded", "false")

    await user.click(toggle)
    expect(toggle).toHaveAttribute("aria-expanded", "true")

    const drawer = screen.getByTestId("monitoring-shell-drawer")
    expect(drawer).toHaveAttribute("role", "dialog")
    expect(drawer).toHaveAttribute("aria-modal", "true")

    const navLinks = screen.getAllByRole("link")
    expect(navLinks.length).toBeGreaterThan(0)
    navLinks[0]?.focus()

    await user.keyboard("{Escape}")
    expect(toggle).toHaveAttribute("aria-expanded", "false")
  })

  it("closes drawer when a nav link is activated", async () => {
    const user = userEvent.setup()
    renderShell(
      <MonitoringShell headline="Test event">
        <div>Board</div>
      </MonitoringShell>,
    )

    await user.click(screen.getByTestId("mobile-menu-open"))
    const dashboardLink = screen.getByTestId("nav-prediction")
    await user.click(dashboardLink)
    expect(screen.getByTestId("mobile-menu-open")).toHaveAttribute("aria-expanded", "false")
  })
})
