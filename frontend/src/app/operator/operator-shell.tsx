import type { ReactNode } from "react"
import { NavLink } from "react-router-dom"

export function OperatorShell({ children }: { children: ReactNode }) {
  return (
    <div className="operator-app min-h-screen">
      <nav className="flex min-h-14 items-center gap-2 border-b border-slate-800 px-4 lg:hidden" aria-label="Operator preview navigation">
        <NavLink to="/preview" end className={({ isActive }) => `min-h-11 px-3 py-3 text-sm ${isActive ? "border-b-2 border-emerald-400 text-white" : "text-slate-400"}`}>Dashboard</NavLink>
        <NavLink to="/preview/lab" className={({ isActive }) => `min-h-11 px-3 py-3 text-sm ${isActive ? "border-b-2 border-emerald-400 text-white" : "text-slate-400"}`}>Lab</NavLink>
      </nav>
      {children}
    </div>
  )
}
