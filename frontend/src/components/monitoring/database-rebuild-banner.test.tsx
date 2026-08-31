import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { DatabaseRebuildBanner } from "@/components/monitoring/database-rebuild-banner"

const snapshotMock = vi.hoisted(() => ({
  dbUnavailable: false,
  dbRestoreInProgress: false,
}))

vi.mock("@/providers/live-snapshot-provider", () => ({
  useLiveSnapshot: () => snapshotMock,
}))

describe("DatabaseRebuildBanner", () => {
  it("renders nothing when the database is healthy", () => {
    snapshotMock.dbUnavailable = false
    snapshotMock.dbRestoreInProgress = false
    const { container } = render(<DatabaseRebuildBanner />)
    expect(container).toBeEmptyDOMElement()
  })

  it("blocks the screen when the database is damaged", () => {
    snapshotMock.dbUnavailable = true
    snapshotMock.dbRestoreInProgress = true
    render(<DatabaseRebuildBanner />)
    expect(screen.getByTestId("db-rebuild-banner")).toHaveAttribute("role", "alert")
    expect(screen.getByText(/backup restore is running/i)).toBeInTheDocument()
  })
})
