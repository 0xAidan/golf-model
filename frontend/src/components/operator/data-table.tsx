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
    <div className="overflow-x-auto border border-slate-800 bg-[#11151a]">
      <table className="w-full min-w-[620px] text-left text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead className="border-b border-slate-800 bg-slate-900/70 text-xs uppercase tracking-[0.1em] text-slate-400">
          <tr>
            {columns.map((column) => <th key={column.id} className={`h-10 px-3 font-medium ${column.align === "right" ? "text-right" : ""}`}>{column.label}</th>)}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800">
          {rows.map((row) => (
            <tr key={row.id} className={onRowClick ? "cursor-pointer hover:bg-slate-800/60 focus-within:bg-slate-800/60" : ""}>
              {columns.map((column, index) => (
                <td key={column.id} className={`h-10 px-3 text-slate-200 ${column.align === "right" ? "text-right operator-num" : ""}`}>
                  {index === 0 && onRowClick ? <button type="button" className="w-full text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-300" onClick={() => onRowClick(row)}>{column.render(row)}</button> : column.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
