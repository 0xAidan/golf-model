import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { FilterSheet } from "@/components/ui/filter-sheet"

vi.mock("@/hooks/use-media-query", () => ({
  useIsNarrowViewport: vi.fn(() => false),
}))

describe("FilterSheet", () => {
  it("renders children inline on wide viewport", () => {
    render(
      <FilterSheet title="Filters">
        <div data-testid="filter-child">Books</div>
      </FilterSheet>,
    )
    expect(screen.getByTestId("filter-child")).toBeInTheDocument()
    expect(screen.queryByTestId("filter-sheet-open")).not.toBeInTheDocument()
  })
})
