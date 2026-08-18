import type { ReactNode } from "react"

export type OperatorColumn<Row> = {
  id: string
  label: ReactNode
  align?: "left" | "right"
  render: (row: Row) => ReactNode
}

export function DataTable<Row extends { id: string }>({
  columns,
  rows,
  caption,
  onRowClick,
}: {
  columns: OperatorColumn<Row>[]
  rows: Row[]
  caption: string
  onRowClick?: (row: Row) => void
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[520px] border-collapse text-left text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr className="border-b border-[var(--op-border)]">
            {columns.map((column) => (
              <th
                key={column.id}
                className={`h-9 px-3 text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--op-text-tertiary)] ${column.align === "right" ? "text-right" : ""}`}
              >
                {column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.id}
              className={`border-b border-[var(--op-border)] last:border-b-0 transition-colors ${onRowClick ? "cursor-pointer hover:bg-[var(--op-surface-2)]" : ""}`}
            >
              {columns.map((column, index) => (
                <td
                  key={column.id}
                  className={`h-12 px-3 text-[var(--op-text)] ${column.align === "right" ? "op-num text-right" : ""}`}
                >
                  {index === 0 && onRowClick ? (
                    <button
                      type="button"
                      className="op-focus w-full text-left"
                      onClick={() => onRowClick(row)}
                    >
                      {column.render(row)}
                    </button>
                  ) : (
                    column.render(row)
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
