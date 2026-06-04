import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { ColumnDef } from "@tanstack/react-table"
import { describe, expect, it } from "vitest"

import { ProDataGrid } from "@/components/ui/pro-data-grid"
import { setTableDensity } from "@/lib/table-density"

type Row = { id: string; name: string; score: number }

const columns: ColumnDef<Row, unknown>[] = [
  {
    id: "name",
    accessorKey: "name",
    header: "Name",
    enableSorting: true,
    meta: { label: "Name" },
  },
  {
    id: "score",
    accessorKey: "score",
    header: "Score",
    enableSorting: true,
    meta: { label: "Score", align: "right", mono: true },
  },
]

describe("ProDataGrid", () => {
  it("renders empty message when data is empty", () => {
    render(<ProDataGrid data={[]} columns={columns} emptyMessage="No rows here" testId="test-grid" />)
    expect(screen.getByTestId("test-grid")).toBeInTheDocument()
    expect(screen.getByText("No rows here")).toBeInTheDocument()
  })

  it("sorts numeric column on header click", async () => {
    const user = userEvent.setup()
    const data: Row[] = [
      { id: "a", name: "Alpha", score: 10 },
      { id: "b", name: "Beta", score: 30 },
      { id: "c", name: "Gamma", score: 20 },
    ]
    render(<ProDataGrid data={data} columns={columns} testId="sort-grid" />)
    const scoreHeader = screen.getByRole("button", { name: /Score/i })
    await user.click(scoreHeader)
    const cells = screen.getAllByRole("cell")
    expect(cells[1]?.textContent).toBe("30")
  })

  it("passes getRowTestId to row elements", () => {
    const data: Row[] = [{ id: "x", name: "X", score: 1 }]
    render(
      <ProDataGrid
        data={data}
        columns={columns}
        getRowTestId={(row) => `row-${row.id}`}
        getRowId={(row) => row.id}
      />,
    )
    expect(screen.getByTestId("row-x")).toBeInTheDocument()
  })

  it("shows density toggle when enabled", async () => {
    const user = userEvent.setup()
    setTableDensity("compact")
    render(
      <ProDataGrid
        data={[{ id: "a", name: "A", score: 1 }]}
        columns={columns}
        showDensityToggle
        testId="density-grid"
      />,
    )
    const comfortable = screen.getByRole("button", { name: /comfortable/i })
    await user.click(comfortable)
    expect(screen.getByRole("button", { name: /compact/i })).toBeInTheDocument()
  })

  it("does not virtualize below threshold", () => {
    const data: Row[] = Array.from({ length: 10 }, (_, i) => ({
      id: String(i),
      name: `P${i}`,
      score: i,
    }))
    render(
      <ProDataGrid data={data} columns={columns} virtualizeAfter={80} testId="small-grid" />,
    )
    expect(screen.getByTestId("small-grid").querySelector(".pro-grid-virtual-scroll")).toBeNull()
  })
})
