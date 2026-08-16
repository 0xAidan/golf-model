import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { RebuildStatusBanner, shouldShowRebuildBanner } from "./rebuild-status-banner"

describe("shouldShowRebuildBanner", () => {
  it("stays hidden during routine freshness warnings", () => {
    expect(shouldShowRebuildBanner({ dbOk: true, rebuildState: "ok" })).toBe(false)
    expect(shouldShowRebuildBanner({ dbOk: null, rebuildState: null })).toBe(false)
  })

  it("shows when the database is down or this week is rebuilding", () => {
    expect(shouldShowRebuildBanner({ dbOk: false, rebuildState: "unavailable" })).toBe(true)
    expect(shouldShowRebuildBanner({ dbOk: true, rebuildState: "rebuilding" })).toBe(true)
  })
})

describe("RebuildStatusBanner", () => {
  it("renders a blocking alert with the rebuild message", () => {
    render(
      <RebuildStatusBanner message="Showing last saved boards while this week is rebuilt." />,
    )
    expect(screen.getByTestId("rebuild-status-banner")).toHaveAttribute("role", "alert")
    expect(screen.getByText("Boards may be out of date")).toBeInTheDocument()
    expect(
      screen.getByText("Showing last saved boards while this week is rebuilt."),
    ).toBeInTheDocument()
  })
})
