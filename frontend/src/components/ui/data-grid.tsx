import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type OnChangeFn,
  type SortingState,
  type VisibilityState,
} from "@tanstack/react-table"
import { useState, type ReactNode } from "react"
import { ChevronDown, ChevronUp } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { cn } from "@/lib/utils"

export type TableDensity = "compact" | "comfortable"

export function DataGrid<T>({
  data,
  columns,
  density = "compact",
  stickyHeader = true,
  columnVisibility: controlledVisibility,
  onColumnVisibilityChange,
  toolbar,
  emptyMessage = "No rows",
  className,
  testId,
  getRowTestId,
}: {
  data: T[]
  columns: ColumnDef<T, unknown>[]
  density?: TableDensity
  stickyHeader?: boolean
  columnVisibility?: VisibilityState
  onColumnVisibilityChange?: OnChangeFn<VisibilityState>
  toolbar?: ReactNode
  emptyMessage?: string
  className?: string
  testId?: string
  getRowTestId?: (row: T) => string | undefined
}) {
  const [sorting, setSorting] = useState<SortingState>([])
  const [internalVisibility, setInternalVisibility] = useState<VisibilityState>({})
  const columnVisibility = controlledVisibility ?? internalVisibility

  const table = useReactTable({
    data,
    columns,
    state: { sorting, columnVisibility },
    onSortingChange: setSorting,
    onColumnVisibilityChange: onColumnVisibilityChange ?? setInternalVisibility,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })

  const hideable = table.getAllColumns().filter((col) => col.getCanHide())

  return (
    <div className={cn("data-grid", className)} data-testid={testId}>
      {(toolbar || hideable.length > 0) && (
        <div className="data-grid-toolbar">
          {toolbar}
          {hideable.length > 0 ? (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button type="button" variant="outline" size="xs" data-testid="data-table-columns">
                  Columns
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="max-h-64 overflow-y-auto">
                {hideable.map((column) => (
                  <DropdownMenuCheckboxItem
                    key={column.id}
                    checked={column.getIsVisible()}
                    onCheckedChange={(value) => column.toggleVisibility(Boolean(value))}
                  >
                    {typeof column.columnDef.header === "string"
                      ? column.columnDef.header
                      : column.id}
                  </DropdownMenuCheckboxItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          ) : null}
        </div>
      )}

      <div className="table-scroll-region">
        <table
          className={cn(
            "data-table",
            "terminal-table",
            stickyHeader && "data-grid--sticky",
            density === "compact" ? "data-grid--compact" : "data-grid--comfortable",
          )}
        >
          <thead>
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <th
                    key={header.id}
                    className={cn(
                      header.column.columnDef.meta?.align === "right" && "num",
                      header.column.getCanSort() && "data-grid-sortable",
                    )}
                    aria-sort={
                      header.column.getIsSorted() === "asc"
                        ? "ascending"
                        : header.column.getIsSorted() === "desc"
                          ? "descending"
                          : undefined
                    }
                  >
                    {header.isPlaceholder ? null : (
                      <button
                        type="button"
                        className="data-grid-sort-btn"
                        onClick={header.column.getToggleSortingHandler()}
                        disabled={!header.column.getCanSort()}
                      >
                        {flexRender(header.column.columnDef.header, header.getContext())}
                        {header.column.getIsSorted() === "asc" ? (
                          <ChevronUp size={12} aria-hidden />
                        ) : header.column.getIsSorted() === "desc" ? (
                          <ChevronDown size={12} aria-hidden />
                        ) : null}
                      </button>
                    )}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="data-grid-empty">
                  {emptyMessage}
                </td>
              </tr>
            ) : (
              table.getRowModel().rows.map((row) => (
                <tr
                  key={row.id}
                  data-testid={getRowTestId?.(row.original)}
                >
                  {row.getVisibleCells().map((cell) => (
                    <td
                      key={cell.id}
                      className={cn(cell.column.columnDef.meta?.align === "right" && "num")}
                    >
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

declare module "@tanstack/react-table" {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  interface ColumnMeta<TData, TValue> {
    align?: "left" | "right"
  }
}
