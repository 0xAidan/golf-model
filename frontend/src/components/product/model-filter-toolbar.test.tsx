import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { ModelFilterToolbar } from "@/components/product/model-filter-toolbar"
import { collectBooksForFilter, SUPPORTED_BOOKS } from "@/lib/prediction-board"

describe("ModelFilterToolbar (book filter regression)", () => {
  it("renders book chips when handlers are provided, even with zero edges", () => {
    render(
      <ModelFilterToolbar
        predictionTab="upcoming"
        availableBooks={["fanduel", "draftkings"]}
        selectedBooks={[]}
        matchupSearch=""
        minEdge={0.02}
        onSelectedBooksChange={vi.fn()}
        onMinEdgeChange={vi.fn()}
        onMatchupSearchChange={vi.fn()}
      />,
    )
    expect(screen.getByTestId("toolbar-book-chip-fanduel")).toBeInTheDocument()
    expect(screen.getByTestId("toolbar-book-chip-draftkings")).toBeInTheDocument()
  })

  it("toggles a book on click and reflects the selected state", () => {
    const handleChange = vi.fn()
    const { rerender } = render(
      <ModelFilterToolbar
        predictionTab="live"
        availableBooks={["fanduel", "draftkings"]}
        selectedBooks={[]}
        matchupSearch=""
        minEdge={0.02}
        onSelectedBooksChange={handleChange}
      />,
    )
    fireEvent.click(screen.getByTestId("toolbar-book-chip-fanduel"))
    expect(handleChange).toHaveBeenCalledWith(["fanduel"])

    rerender(
      <ModelFilterToolbar
        predictionTab="live"
        availableBooks={["fanduel", "draftkings"]}
        selectedBooks={["fanduel"]}
        matchupSearch=""
        minEdge={0.02}
        onSelectedBooksChange={handleChange}
      />,
    )
    const activeChip = screen.getByTestId("toolbar-book-chip-fanduel")
    expect(activeChip).toHaveAttribute("aria-pressed", "true")
    expect(screen.getByTestId("toolbar-book-chip-clear")).toBeInTheDocument()
  })

  it("clears all books via the clear control", () => {
    const handleChange = vi.fn()
    render(
      <ModelFilterToolbar
        predictionTab="live"
        availableBooks={["fanduel", "draftkings"]}
        selectedBooks={["fanduel"]}
        matchupSearch=""
        minEdge={0.02}
        onSelectedBooksChange={handleChange}
      />,
    )
    fireEvent.click(screen.getByTestId("toolbar-book-chip-clear"))
    expect(handleChange).toHaveBeenCalledWith([])
  })

  it("stays display-only (no chips) when no handlers are supplied", () => {
    render(
      <ModelFilterToolbar
        predictionTab="upcoming"
        availableBooks={["fanduel"]}
        selectedBooks={[]}
        matchupSearch=""
        minEdge={0.05}
      />,
    )
    expect(screen.queryByTestId("toolbar-book-chip-fanduel")).not.toBeInTheDocument()
    expect(screen.getByTestId("filter-summary-chip")).toHaveTextContent("All books")
    expect(screen.getByTestId("filter-summary-chip")).toHaveTextContent("5% min edge")
  })
})

describe("collectBooksForFilter", () => {
  it("falls back to SUPPORTED_BOOKS when no run rows and no books_seen", () => {
    expect(collectBooksForFilter(null, [])).toEqual([...SUPPORTED_BOOKS].sort())
  })

  it("unions run books with snapshot books_seen and drops non-book sources", () => {
    const run = {
      matchup_bets_all_books: [{ book: "FanDuel" }, { book: "datagolf" }],
      value_bets: {},
    } as never
    const result = collectBooksForFilter(run, ["BetMGM", "fanduel"])
    expect(result).toContain("fanduel")
    expect(result).toContain("betmgm")
    expect(result).not.toContain("datagolf")
  })
})
