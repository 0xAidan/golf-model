import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type OnChangeFn,
  type Row,
  type SortingState,
  type VisibilityState,
} from "@tanstack/react-table"
import { useVirtualizer } from "@tanstack/react-virtual"
import { ChevronDown, ChevronUp } from "lucide-react"
import { Fragment, useRef, useState, type ReactNode } from "react"

import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { useOddsFlashMap } from "@/hooks/use-odds-flash"
import { setTableDensity, useTableDensity, type TableDensityPreference } from "@/lib/table-density"
import { cn } from "@/lib/utils"

export type TableDensity = "compact" | "comfortable"

export type ProDataGridProps<T> = {
  data: T[]
  columns: ColumnDef<T, unknown>[]
  density?: TableDensity
  stickyHeader?: boolean
  virtualizeAfter?: number
  columnVisibility?: VisibilityState
  onColumnVisibilityChange?: OnChangeFn<VisibilityState>
  toolbar?: ReactNode
  emptyMessage?: string
  isLoading?: boolean
  loadingMessage?: string
  className?: string
  testId?: string
  getRowTestId?: (row: T) => string | undefined
  onRowClick?: (row: T) => void
  renderSubRow?: (row: T) => ReactNode
  expandedRowId?: string | null
  getRowId?: (row: T) => string
  getOddsForFlash?: (row: T) => number | string | null | undefined
  getRowClassName?: (row: T) => string | undefined
  showDensityToggle?: boolean
}

const COMPACT_ROW = 32
const COMFORTABLE_ROW = 40

export function ProDataGrid<T>({
  data,
  columns,
  density: densityProp,
  stickyHeader = true,
  virtualizeAfter = 80,
  columnVisibility: controlledVisibility,
  onColumnVisibilityChange,
  toolbar,
  emptyMessage = "No rows",
  isLoading = false,
  loadingMessage = "Loading rows…",
  className,
  testId = "pro-data-grid",
  getRowTestId,
  onRowClick,
  renderSubRow,
  expandedRowId,
  getRowId,
  getOddsForFlash,
  getRowClassName,
  showDensityToggle = false,
}: ProDataGridProps<T>) {
  const globalDensity = useTableDensity()
  const effectiveDensity = showDensityToggle
    ? globalDensity
    : (densityProp ?? globalDensity)
  const [sorting, setSorting] = useState<SortingState>([])
  const [internalVisibility, setInternalVisibility] = useState<VisibilityState>({})
  const columnVisibility = controlledVisibility ?? internalVisibility
  const scrollRef = useRef<HTMLDivElement>(null)

  const table = useReactTable({
    data,
    columns,
    state: { sorting, columnVisibility },
    onSortingChange: setSorting,
    onColumnVisibilityChange: onColumnVisibilityChange ?? setInternalVisibility,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getRowId: getRowId ? (row) => getRowId(row) : undefined,
  })

  const rows = table.getRowModel().rows
  const hideable = table.getAllColumns().filter((col) => col.getCanHide())
  const shouldVirtualize = rows.length >= virtualizeAfter
  const rowHeight = effectiveDensity === "compact" ? COMPACT_ROW : COMFORTABLE_ROW

  const flashMap = useOddsFlashMap(
    getOddsForFlash && getRowId ? data : [],
    (row) => (getRowId ? getRowId(row) : ""),
    (row) => (getOddsForFlash ? getOddsForFlash(row) : null),
  )

  const handleDensityChange = (next: TableDensityPreference) => {
    setTableDensity(next)
  }

  const renderRow = (row: Row<T>, style?: { height?: number }) => {
    const rowId = getRowId?.(row.original) ?? row.id
    const isExpanded = expandedRowId != null && expandedRowId === rowId
    const subRow = isExpanded && renderSubRow ? renderSubRow(row.original) : null
    const flash = getRowId ? flashMap[getRowId(row.original)] : undefined

    return (
      <Fragment key={row.id}>
        <tr
          data-testid={getRowTestId?.(row.original)}
          onClick={onRowClick ? () => onRowClick(row.original) : undefined}
          className={cn(
            onRowClick && "terminal-row-clickable",
            isExpanded && "terminal-row-expanded",
            flash === "up" && "terminal-row-flash-up",
            flash === "down" && "terminal-row-flash-down",
            getRowClassName?.(row.original),
          )}
          style={style}
        >
          {row.getVisibleCells().map((cell, cellIdx) => (
            <td
              key={cell.id}
              className={cn(
                cell.column.columnDef.meta?.align === "right" && "num terminal-cell-numeric",
                cell.column.columnDef.meta?.align === "center" && "center",
                cell.column.columnDef.meta?.mono && "terminal-cell-numeric",
                cellIdx === 0 && cell.column.columnDef.meta?.sticky && "pro-grid-sticky-col",
              )}
            >
              {flexRender(cell.column.columnDef.cell, cell.getContext())}
            </td>
          ))}
        </tr>
        {subRow ? (
          <tr className="terminal-sub-row">
            <td colSpan={row.getVisibleCells().length}>{subRow}</td>
          </tr>
        ) : null}
      </Fragment>
    )
  }

  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => rowHeight,
    overscan: 8,
    enabled: shouldVirtualize,
  })

  const virtualRows = shouldVirtualize ? virtualizer.getVirtualItems() : null

  const tbodyContent = (() => {
    if (isLoading) {
      return (
        <tr>
          <td colSpan={columns.length} className="data-grid-loading" data-testid="data-grid-loading">
            {loadingMessage}
          </td>
        </tr>
      )
    }

    if (rows.length === 0) {
      return (
        <tr>
          <td colSpan={columns.length} className="data-grid-empty">
            {emptyMessage}
          </td>
        </tr>
      )
    }

    if (!shouldVirtualize || !virtualRows) {
      return rows.map((row) => renderRow(row))
    }

    const paddingTop = virtualRows.length > 0 ? virtualRows[0]?.start ?? 0 : 0
    const paddingBottom =
      virtualRows.length > 0
        ? virtualizer.getTotalSize() - (virtualRows[virtualRows.length - 1]?.end ?? 0)
        : 0

    return (
      <>
        {paddingTop > 0 ? (
          <tr aria-hidden>
            <td colSpan={columns.length} style={{ height: paddingTop, padding: 0, border: 0 }} />
          </tr>
        ) : null}
        {virtualRows.map((virtualRow) => {
          const row = rows[virtualRow.index]
          if (!row) return null
          return renderRow(row, { height: virtualRow.size })
        })}
        {paddingBottom > 0 ? (
          <tr aria-hidden>
            <td colSpan={columns.length} style={{ height: paddingBottom, padding: 0, border: 0 }} />
          </tr>
        ) : null}
      </>
    )
  })()

  return (
    <div className={cn("data-grid pro-data-grid", className)} data-testid={testId}>
      {(toolbar || hideable.length > 0 || showDensityToggle) && (
        <div className="data-grid-toolbar">
          {toolbar}
          {showDensityToggle ? (
            <div className="data-grid-density-toggle" role="group" aria-label="Table density">
              <Button
                type="button"
                variant={effectiveDensity === "compact" ? "default" : "outline"}
                size="xs"
                data-testid="data-table-density-compact"
                onClick={() => handleDensityChange("compact")}
              >
                Compact
              </Button>
              <Button
                type="button"
                variant={effectiveDensity === "comfortable" ? "default" : "outline"}
                size="xs"
                data-testid="data-table-density-comfortable"
                onClick={() => handleDensityChange("comfortable")}
              >
                Comfortable
              </Button>
            </div>
          ) : null}
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
                    {column.columnDef.meta?.label ??
                      (typeof column.columnDef.header === "string"
                        ? column.columnDef.header
                        : column.id)}
                  </DropdownMenuCheckboxItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          ) : null}
        </div>
      )}

      <div
        ref={scrollRef}
        className={cn("table-scroll-region", shouldVirtualize && "pro-grid-virtual-scroll")}
      >
        <table
          className={cn(
            "data-table",
            "terminal-table",
            stickyHeader && "data-grid--sticky",
            effectiveDensity === "compact" ? "data-grid--compact" : "data-grid--comfortable",
          )}
        >
          <thead>
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map((header, headerIdx) => (
                  <th
                    key={header.id}
                    className={cn(
                      header.column.columnDef.meta?.align === "right" && "num",
                      header.column.columnDef.meta?.align === "center" && "center",
                      header.column.getCanSort() && "data-grid-sortable",
                      headerIdx === 0 && header.column.columnDef.meta?.sticky && "pro-grid-sticky-col",
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
          <tbody>{tbodyContent}</tbody>
        </table>
      </div>
    </div>
  )
}

declare module "@tanstack/react-table" {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  interface ColumnMeta<TData, TValue> {
    align?: "left" | "right" | "center"
    mono?: boolean
    sticky?: boolean
    label?: string
    hideable?: boolean
  }
}

/** @deprecated Use ProDataGrid */
export { ProDataGrid as DataGrid }
