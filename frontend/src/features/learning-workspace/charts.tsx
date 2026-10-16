import { useState } from "react"
import type { PerformanceEvent, PerformanceScope } from "./types"

export const number = (v: number | null | undefined, digits = 1) => typeof v === "number" && Number.isFinite(v) ? v.toLocaleString("en", { minimumFractionDigits: digits, maximumFractionDigits: digits }) : "—"
export const signed = (v: number | null | undefined, suffix = "", digits = 1) => typeof v === "number" && Number.isFinite(v) ? `${v > 0 ? "+" : ""}${number(v, digits)}${suffix}` : "—"
export const shortDate = (v: string | undefined) => {
  if (!v) return "Date unavailable"
  const d = new Date(v.length === 10 ? `${v}T12:00:00Z` : v)
  return Number.isNaN(d.getTime()) ? "Date unavailable" : d.toLocaleDateString("en", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" })
}

export function EquityChart({ series }: { series: PerformanceEvent[] }) {
  const [hover, setHover] = useState<number | null>(null)
  const selected = series[Math.min(hover ?? series.length - 1, series.length - 1)]
  const values = [0, ...series.map(row => row.cumulative_profit)]
  const lo = Math.min(...values), hi = Math.max(...values)
  const spread = Math.max(hi - lo, 2)
  const min = lo - spread * .14, max = hi + spread * .14
  const x = (i: number) => 54 + i / Math.max(series.length, 1) * 890
  const y = (v: number) => 220 - (v - min) / (max - min) * 195
  const points = values.map((v, i) => `${x(i)},${y(v)}`).join(" ")
  if (!series.length) return <div className="lw-empty"><h3>No settled records in this scope.</h3><p>Try another market or model lane.</p></div>
  return <div className="lw-equity">
    <div className="lw-chart-readout"><div><strong>{selected?.event_name}</strong><span>{shortDate(selected?.event_start)} · {selected?.decisions} selections</span></div><div><strong className={(selected?.unit_profit ?? 0) >= 0 ? "lw-positive" : "lw-negative"}>{signed(selected?.unit_profit, "u")}</strong><span>Event paper return</span></div></div>
    <svg viewBox="0 0 980 255" role="img" aria-label={`Cumulative paper return across ${series.length} events, ending at ${signed(series.at(-1)?.cumulative_profit, " units")}.`} onPointerMove={event => {const r = event.currentTarget.getBoundingClientRect(); const chartX = (event.clientX - r.left) / r.width * 980; setHover(Math.max(0, Math.min(series.length - 1, Math.round((chartX - 54) / 890 * series.length) - 1)))}} onPointerLeave={() => setHover(null)}>
      {[0, 1, 2, 3].map(i => { const value = min + (max - min) * i / 3; return <g key={i}><line x1="54" x2="944" y1={y(value)} y2={y(value)} className="lw-chart-grid"/><text x="43" y={y(value) + 4} textAnchor="end">{number(value, 0)}u</text></g> })}
      <line x1="54" x2="944" y1={y(0)} y2={y(0)} className="lw-chart-zero"/>
      <polyline points={points} fill="none" className="lw-equity-line"/>
      {selected && <><line x1={x((hover ?? series.length - 1) + 1)} x2={x((hover ?? series.length - 1) + 1)} y1="25" y2="220" className="lw-chart-guide"/><circle cx={x((hover ?? series.length - 1) + 1)} cy={y(selected.cumulative_profit)} r="5" className="lw-chart-dot"/></>}
      <text x="54" y="248">{shortDate(series[0]?.event_start)}</text><text x="944" y="248" textAnchor="end">{shortDate(series.at(-1)?.event_start)}</text>
    </svg>
    <label className="lw-chart-slider">Inspect event<input aria-label="Inspect event in return chart" type="range" min="0" max={series.length - 1} value={hover ?? series.length - 1} onChange={event => setHover(Number(event.target.value))}/><span>{(hover ?? series.length - 1) + 1} / {series.length}</span></label>
  </div>
}

export function CalibrationPlot({ bins }: { bins: PerformanceScope["reliability"] }) {
  if (!bins.some(b => b.n > 0)) return <p className="lw-muted">No binary forecasts with a valid probability in this scope.</p>
  return <svg className="lw-calibration" viewBox="0 0 400 260" role="img" aria-label="Calibration: forecast probability compared with observed win rate. The diagonal is perfect calibration.">
    {[0, .25, .5, .75, 1].map(v => <g key={v}><line x1="45" x2="365" y1={215 - v * 180} y2={215 - v * 180} className="lw-chart-grid"/><text x="35" y={219 - v * 180} textAnchor="end">{v * 100}%</text><text x={45 + v * 320} y="236" textAnchor="middle">{v * 100}%</text></g>)}
    <line x1="45" y1="215" x2="365" y2="35" className="lw-chart-guide"/>
    {bins.filter(b => b.n > 0).map((b, i) => <circle key={i} cx={45 + b.predicted * 320} cy={215 - b.observed * 180} r={Math.max(4, Math.min(10, Math.sqrt(b.n) * 1.3))} className="lw-calibration-dot"><title>{number(b.predicted * 100)}% forecast · {number(b.observed * 100)}% observed · {b.n} records</title></circle>)}
    <text x="205" y="258" textAnchor="middle">Forecast probability</text>
  </svg>
}
