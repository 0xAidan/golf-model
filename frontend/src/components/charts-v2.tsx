/**
 * charts-v2.tsx
 * Creative, distinctive data visualizations for Golf Model player profiles.
 * All pure React + SVG — no new dependencies.
 *
 * Exports:
 *  - PentagonRadar        — 5-axis skill radar (SVG; per-axis heat spectrum)
 *  - BeeswarmStrip        — field distribution, player highlighted
 *  - RollingBarLine       — per-round bars + moving average line, stat tabs
 *  - ApproachArcGauges    — semicircle arc per yardage bucket
 *  - HistoryTable         — finish chips + inline SG bars
 */

import { useLayoutEffect, useRef, useState } from "react"
import ReactECharts from "echarts-for-react"
import { heatSpectrumHexFromUnit } from "@/lib/metric-heat"

/* ── Design tokens ───────────────────────────────────────────────────── */
const T = {
  bg: "var(--bg)",
  bg1: "var(--bg-1)",
  bg2: "var(--bg-2)",
  surface: "var(--surface)",
  border: "var(--border)",
  divider: "var(--divider)",
  text: "var(--text)",
  muted: "var(--text-muted)",
  faint: "var(--text-faint)",
  green: "var(--green)",
  greenBg: "var(--green-bg)",
  greenDim: "var(--green-dim)",
  gold: "var(--gold)",
  goldBg: "rgba(245, 180, 24, 0.14)",
  goldDim: "rgba(245, 180, 24, 0.33)",
  red: "var(--red)",
  redBg: "var(--red-bg)",
  redDim: "rgba(239, 68, 68, 0.22)",
  mono: "var(--font-mono)",
}

const TOOLTIP = {
  backgroundColor: T.bg,
  borderColor: T.border,
  borderWidth: 1,
  textStyle: { color: T.text, fontSize: 11, fontFamily: T.mono },
  extraCssText: "border-radius:3px;box-shadow:0 4px 16px rgba(0,0,0,0.5);",
}

/* ── Shared helpers ──────────────────────────────────────────────────── */
function ChartEmpty({ height = 120, msg = "No data" }: { height?: number; msg?: string }) {
  return (
    <div style={{
      height, display: "flex", alignItems: "center", justifyContent: "center",
      background: T.surface, border: `1px dashed ${T.border}`, borderRadius: 3,
      fontFamily: T.mono, fontSize: 10, letterSpacing: "0.08em",
      textTransform: "uppercase", color: T.faint,
    }}>
      {msg}
    </div>
  )
}

function signed(v: number, d = 3) { return `${v > 0 ? "+" : ""}${v.toFixed(d)}` }

function ordinalPct(n: number): string {
  const m10 = n % 10
  const m100 = n % 100
  if (m100 >= 11 && m100 <= 13) return `${n}th`
  if (m10 === 1) return `${n}st`
  if (m10 === 2) return `${n}nd`
  if (m10 === 3) return `${n}rd`
  return `${n}th`
}

/* ══════════════════════════════════════════════════════════════════════
   1. PENTAGON RADAR — 5-axis skill profile
   ══════════════════════════════════════════════════════════════════════ */
export type RadarSkills = {
  sg_ott?:  number | null
  sg_app?:  number | null
  sg_arg?:  number | null
  sg_putt?: number | null
  sg_total?: number | null
}

/** Radar chrome — concrete RGBA (readable on dark UI). */
const RADAR_GRID_LINE = "rgba(139, 156, 169, 0.38)"
const RADAR_GRID_AXIS = "rgba(139, 156, 169, 0.32)"
const RADAR_TOUR_LINE = "rgba(155, 170, 180, 0.9)"

const SKILL_PROFILE_HEAT_ABS = 2.5

function axisHeatHexFromRaw(raw: number | null | undefined): string {
  if (raw == null || !Number.isFinite(raw)) return heatSpectrumHexFromUnit(0.5)
  const u = Math.min(1, Math.max(0, (raw + SKILL_PROFILE_HEAT_ABS) / (SKILL_PROFILE_HEAT_ABS * 2)))
  return heatSpectrumHexFromUnit(u)
}

function hexToRgbTuple(hex: string): [number, number, number] {
  const m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex.trim())
  if (!m) return [107, 122, 132]
  return [parseInt(m[1], 16), parseInt(m[2], 16), parseInt(m[3], 16)]
}

function averageHexColors(hexes: string[]): string {
  if (hexes.length === 0) return "#808080"
  let r = 0, g = 0, b = 0
  for (const h of hexes) {
    const [rr, gg, bb] = hexToRgbTuple(h)
    r += rr
    g += gg
    b += bb
  }
  const n = hexes.length
  return `#${[r / n, g / n, b / n].map((c) => Math.round(c).toString(16).padStart(2, "0")).join("")}`
}

function mixHex(a: string, b: string, t: number): string {
  const [ar, ag, ab] = hexToRgbTuple(a)
  const [br, bg, bb] = hexToRgbTuple(b)
  const u = Math.min(1, Math.max(0, t))
  const r = ar + (br - ar) * u
  const g = ag + (bg - ag) * u
  const bl = ab + (bb - ab) * u
  return `#${[r, g, bl].map((c) => Math.round(c).toString(16).padStart(2, "0")).join("")}`
}

/**
 * Convert raw SG values to 0–100 percentile-style scale for radar.
 * Tour range approx: elite ~+2.0, average 0.0, poor ~-2.0
 * We map [-2.5, +2.5] → [0, 100]
 */
function sgToPercentile(v: number | null | undefined, maxAbs = 2.5): number {
  if (v == null) return 50
  return Math.min(100, Math.max(0, ((v + maxAbs) / (maxAbs * 2)) * 100))
}

export function PentagonRadar({
  skills,
  playerName = "Player",
  height = 300,
}: {
  skills: RadarSkills
  playerName?: string
  height?: number
}) {
  const axes = [
    { key: "sg_ott",  label: "Off the Tee",   maxAbs: 1.8 },
    { key: "sg_app",  label: "Approach",       maxAbs: 2.0 },
    { key: "sg_arg",  label: "Around Green",   maxAbs: 1.5 },
    { key: "sg_putt", label: "Putting",        maxAbs: 1.5 },
    { key: "sg_total","label": "Total SG",     maxAbs: 2.8 },
  ] as const

  const legendBandH = 36
  const svgPx = Math.max(160, height - legendBandH)

  const n = axes.length
  const VB_W = 460
  const VB_H = 330
  const cx = VB_W / 2
  const cy = VB_H / 2 + 4
  const R = 100
  const ringFracs = [0.25, 0.5, 0.75, 1]
  /** First axis at top, then clockwise (ECharts radar default). */
  const angleAt = (i: number) => -Math.PI / 2 - (i * 2 * Math.PI) / n

  const rawByAxis = axes.map(
    (a) => (skills as Record<string, number | null | undefined>)[a.key] as number | null | undefined,
  )
  const playerVals = axes.map((a, i) => sgToPercentile(rawByAxis[i], a.maxAbs))
  const axisHeatHex = rawByAxis.map((raw) => axisHeatHexFromRaw(raw))
  const vertexColors = axisHeatHex

  const pctToR = (pct: number) => (pct / 100) * R
  const pt = (pct: number, i: number) => {
    const a = angleAt(i)
    const r = pctToR(pct)
    return { x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) }
  }

  const tourPoints = axes.map((_, i) => pt(50, i))
  const playerPoints = axes.map((_, i) => pt(playerVals[i] ?? 50, i))

  const tourPoly = tourPoints.map((p) => `${p.x},${p.y}`).join(" ")
  const playerPoly = playerPoints.map((p) => `${p.x},${p.y}`).join(" ")

  const fillAverage = averageHexColors(vertexColors)

  const edgeStroke = (i: number) => {
    const a = vertexColors[i]!
    const b = vertexColors[(i + 1) % n]!
    return mixHex(a, b, 0.5)
  }

  return (
    <div style={{ minHeight: height, fontFamily: T.mono }}>
      <svg
        width="100%"
        height={svgPx}
        viewBox={`0 0 ${VB_W} ${VB_H}`}
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label={`${playerName} skill profile vs tour average`}
      >

        {ringFracs.map((fr) => {
          const ring = axes.map((_, i) => {
            const a = angleAt(i)
            const r = R * fr
            return `${cx + r * Math.cos(a)},${cy + r * Math.sin(a)}`
          }).join(" ")
          return (
            <polygon
              key={fr}
              points={ring}
              fill="none"
              stroke={RADAR_GRID_LINE}
              strokeWidth={fr === 1 ? 1.1 : 0.85}
            />
          )
        })}

        {axes.map((_, i) => {
          const outer = pt(100, i)
          return (
            <line
              key={i}
              x1={cx}
              y1={cy}
              x2={outer.x}
              y2={outer.y}
              stroke={RADAR_GRID_AXIS}
              strokeWidth={1}
            />
          )
        })}

        <polygon
          points={tourPoly}
          fill="none"
          stroke={RADAR_TOUR_LINE}
          strokeWidth={1.5}
          strokeDasharray="5 4"
          strokeLinejoin="round"
        />

        <polygon
          points={playerPoly}
          fill={fillAverage}
          fillOpacity={0.22}
          stroke="none"
        />

        {axes.map((_, i) => {
          const a = playerPoints[i]!
          const b = playerPoints[(i + 1) % n]!
          return (
            <line
              key={`e-${i}`}
              x1={a.x}
              y1={a.y}
              x2={b.x}
              y2={b.y}
              stroke={edgeStroke(i)}
              strokeWidth={2.75}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          )
        })}

        {axes.map((ax, i) => {
          const p = playerPoints[i]!
          const raw = rawByAxis[i]
          const LABEL_R_MULT = 1.26
          const labelPt = pt(100 * LABEL_R_MULT, i)
          const disp = raw != null && Number.isFinite(raw) ? signed(raw) : "—"
          return (
            <g key={ax.key}>
              <circle
                cx={p.x}
                cy={p.y}
                r={6}
                fill={vertexColors[i]}
                stroke="rgba(8, 10, 11, 0.65)"
                strokeWidth={1}
              >
                <title>{`${ax.label}: ${disp} SG (heat spectrum)`}</title>
              </circle>
              <text
                x={labelPt.x}
                y={labelPt.y}
                textAnchor="middle"
                dominantBaseline="middle"
                fill={T.muted}
                fontSize={12}
                fontWeight={600}
                fontFamily={T.mono}
                style={{ letterSpacing: "0.04em" }}
              >
                {ax.label}
              </text>
            </g>
          )
        })}
      </svg>

      <div
        style={{
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
          gap: 20,
          paddingTop: 4,
          paddingBottom: 2,
          flexWrap: "wrap",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span
            style={{
              width: 14,
              height: 8,
              background: RADAR_TOUR_LINE,
              borderRadius: 2,
              opacity: 0.95,
            }}
            aria-hidden
          />
          <span style={{ fontSize: 11, color: T.muted, letterSpacing: "0.04em" }}>Tour Average</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span
            style={{
              width: 28,
              height: 8,
              borderRadius: 2,
              background: `linear-gradient(90deg, ${vertexColors.join(", ")})`,
            }}
            aria-hidden
          />
          <span style={{ fontSize: 11, color: fillAverage, fontWeight: 600, letterSpacing: "0.02em", maxWidth: 240, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{playerName}</span>
        </div>
      </div>
    </div>
  )
}

/* ══════════════════════════════════════════════════════════════════════
   2. BEESWARM STRIP — field distribution, player highlighted
   ══════════════════════════════════════════════════════════════════════ */
export type BeeswarmCategory = {
  label: string
  shortLabel: string
  playerValue: number | null | undefined
  /** If provided, use these as the field. Otherwise we generate a synthetic field. */
  fieldValues?: number[]
}

/**
 * Generates a realistic synthetic PGA Tour field distribution
 * centered around 0 with given std dev.
 */
function syntheticField(n: number, std: number, seed: number): number[] {
  // Seeded LCG random
  let s = seed
  const rand = () => { s = (s * 1664525 + 1013904223) & 0xffffffff; return (s >>> 0) / 0xffffffff }
  // Box-Muller normal
  const normal = () => {
    const u = rand(), v = rand()
    return Math.sqrt(-2 * Math.log(u + 0.0001)) * Math.cos(2 * Math.PI * v)
  }
  return Array.from({ length: n }, () => parseFloat((normal() * std).toFixed(3)))
}

export function BeeswarmStrip({
  categories,
  height = 240,
}: {
  categories: BeeswarmCategory[]
  height?: number
}) {
  const wrapRef = useRef<HTMLDivElement>(null)
  const [measureW, setMeasureW] = useState(720)

  useLayoutEffect(() => {
    const el = wrapRef.current
    if (!el) return
    const update = () => {
      const w = el.getBoundingClientRect().width
      setMeasureW(Math.max(460, Math.floor(w)))
    }
    update()
    const ro = new ResizeObserver(update)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  if (!categories.length) return <ChartEmpty height={height} msg="No field data" />

  const LABEL_COL_W = 96
  const STAT_COL_W = 78
  const PAD_R_EDGE = 10
  const W = Math.max(460, measureW)
  const CHART_W = Math.max(200, W - LABEL_COL_W - STAT_COL_W - PAD_R_EDGE)
  const ROW_H = 48
  const TOP_PAD = 18
  const AXIS_GAP = 14
  const TICK_BAND = 18
  const AXIS_TITLE_H = 16
  const lastRowCenterY = TOP_PAD + (categories.length - 1) * ROW_H
  const axisY = lastRowCenterY + ROW_H / 2 + AXIS_GAP
  const tickLabelY = axisY + TICK_BAND
  const totalH = tickLabelY + AXIS_TITLE_H + 12
  const DOT_R = 4
  const PLAYER_R = 6

  function positionDots(
    vals: number[],
    range: [number, number],
    toXCoord: (v: number) => number,
  ): { x: number; y: number; v: number }[] {
    const [lo, hi] = range
    const toX = (v: number) => toXCoord(v)

    const dots: { x: number; y: number; v: number }[] = []
    const sorted = [...vals].map(v => ({ v, x: toX(v) })).sort((a, b) => a.x - b.x)

    for (const d of sorted) {
      let y = 0
      let placed = false
      for (let dy = 0; dy <= 16; dy += 2) {
        for (const sign of [1, -1]) {
          const tryY = sign * dy
          const collide = dots.some((p) => Math.abs(p.x - d.x) < DOT_R * 2.2 && Math.abs(p.y - tryY) < DOT_R * 2.2)
          if (!collide) {
            y = tryY
            placed = true
            break
          }
        }
        if (placed) break
      }
      dots.push({ x: d.x, y, v: d.v })
    }
    return dots
  }

  const chartLeft = LABEL_COL_W
  const chartRight = chartLeft + CHART_W
  const statsLeft = chartRight + 6

  const allVals = categories.flatMap((c) => {
    const field = c.fieldValues ?? syntheticField(120, 0.7, categories.indexOf(c) * 137 + 42)
    return field
  })
  const globalLo = Math.min(...allVals) - 0.3
  const globalHi = Math.max(...allVals) + 0.3
  const range: [number, number] = [Math.min(globalLo, -2), Math.max(globalHi, 2)]

  const ticks = [-2, -1, 0, 1, 2].filter((t) => t >= range[0] && t <= range[1])
  const toXAxis = (v: number) => chartLeft + ((v - range[0]) / (range[1] - range[0])) * CHART_W

  return (
    <div ref={wrapRef} style={{ width: "100%", minHeight: Math.min(height, totalH), overflowX: "auto" }}>
      <svg
        viewBox={`0 0 ${W} ${totalH}`}
        style={{ width: "100%", display: "block", fontFamily: T.mono }}
        aria-label="Beeswarm field distribution"
      >
        <line x1={chartLeft} y1={axisY} x2={chartRight} y2={axisY} stroke={T.border} strokeWidth={1} />

        {ticks.map((t) => (
          <g key={t}>
            <line x1={toXAxis(t)} y1={axisY - 3} x2={toXAxis(t)} y2={axisY + 3} stroke={T.faint} strokeWidth={1} />
            <text x={toXAxis(t)} y={tickLabelY} textAnchor="middle" fill={T.muted} fontSize={10} letterSpacing={0.4}>
              {t > 0 ? `+${t}` : t}
            </text>
          </g>
        ))}

        <line x1={toXAxis(0)} y1={12} x2={toXAxis(0)} y2={axisY} stroke={T.border} strokeWidth={1} strokeDasharray="3 3" />

        {categories.map((cat, ci) => {
          const cy = TOP_PAD + ci * ROW_H
          const fieldVals = cat.fieldValues ?? syntheticField(120, 0.7, ci * 137 + 42)
          const toXPlot = (v: number) => chartLeft + ((v - range[0]) / (range[1] - range[0])) * CHART_W
          const dots = positionDots(fieldVals, range, toXPlot)

          const pv = cat.playerValue
          const px = pv != null ? toXPlot(pv) : null
          const pcol = pv != null ? (pv >= 0 ? T.green : T.red) : T.muted

          const rank =
            pv != null
              ? Math.round((fieldVals.filter((v) => v <= pv).length / fieldVals.length) * 100)
              : null

          return (
            <g key={ci}>
              <text
                x={chartLeft - 10}
                y={cy + 4}
                textAnchor="end"
                fill={T.text}
                fontSize={11}
                fontWeight={600}
                letterSpacing={0.06}
              >
                {cat.shortLabel}
              </text>

              {dots.map((d, di) => (
                <circle key={di} cx={d.x} cy={cy + d.y} r={DOT_R - 1} fill={T.faint} opacity={0.55} />
              ))}

              {[25, 50, 75].map((pct) => {
                const sorted = [...fieldVals].sort((a, b) => a - b)
                const qv = sorted[Math.floor((pct / 100) * sorted.length)]
                return (
                  <line
                    key={pct}
                    x1={toXPlot(qv)}
                    y1={cy - 11}
                    x2={toXPlot(qv)}
                    y2={cy + 11}
                    stroke={T.border}
                    strokeWidth={1}
                    strokeDasharray={pct === 50 ? "none" : "2 2"}
                  />
                )
              })}

              {px != null && pv != null && (
                <>
                  <circle cx={px} cy={cy} r={PLAYER_R} fill={pcol} opacity={0.95} />
                  <circle cx={px} cy={cy} r={PLAYER_R + 3} fill="none" stroke={pcol} strokeWidth={1} opacity={0.38} />
                  <text x={statsLeft} y={cy - 5} textAnchor="start" fill={pcol} fontSize={11} fontWeight={700}>
                    {signed(pv, 2)}
                  </text>
                  {rank != null && (
                    <text
                      x={statsLeft}
                      y={cy + 9}
                      textAnchor="start"
                      fill={rank >= 75 ? T.green : rank >= 50 ? T.muted : T.red}
                      fontSize={10}
                      fontWeight={600}
                    >
                      {ordinalPct(rank)} pct
                    </text>
                  )}
                </>
              )}

              {ci < categories.length - 1 && (
                <line
                  x1={chartLeft}
                  y1={cy + ROW_H / 2 + 6}
                  x2={chartRight}
                  y2={cy + ROW_H / 2 + 6}
                  stroke={T.divider}
                  strokeWidth={1}
                />
              )}
            </g>
          )
        })}

        <text x={chartLeft + CHART_W / 2} y={totalH - 2} textAnchor="middle" fill={T.muted} fontSize={10} letterSpacing={0.06}>
          Strokes gained / round vs tour average (0)
        </text>
      </svg>
    </div>
  )
}

/* ══════════════════════════════════════════════════════════════════════
   3. ROLLING BAR + LINE CHART — per round bars + moving average
   ══════════════════════════════════════════════════════════════════════ */
export type RollingEvent = {
  event_name: string
  avg_sg_total?:  number | null
  avg_sg_ott?:    number | null
  avg_sg_app?:    number | null
  avg_sg_arg?:    number | null
  avg_sg_putt?:   number | null
  avg_sg_t2g?:    number | null
  avg_to_par?:    number | null
  rounds_played?: number
  fin_text?:      string | null
  event_completed?: string | null
  course_name?: string | null
}

type RollingTab = "TOTAL" | "APP" | "ARG" | "PUTT" | "OTT" | "T2G"
type RollingView = "events" | "rounds"

const ROLLING_TABS: RollingTab[] = ["TOTAL", "APP", "ARG", "PUTT", "OTT", "T2G"]

const ROLLING_KEY: Record<RollingTab, keyof RollingEvent> = {
  TOTAL: "avg_sg_total",
  APP:   "avg_sg_app",
  ARG:   "avg_sg_arg",
  PUTT:  "avg_sg_putt",
  OTT:   "avg_sg_ott",
  T2G:   "avg_sg_t2g",
}

const ROLLING_SCALE_ABS = 2.5
const heatUnitForRolling = (value: number) => Math.min(1, Math.max(0, (value + ROLLING_SCALE_ABS) / (ROLLING_SCALE_ABS * 2)))

/** ECharts often ignores `linear-gradient(...)` and `var(--*)` in series styles — use hex / RGBA literals. */
const ROLLING_EC = {
  text: "#e8ecef",
  muted: "#6b7a84",
  faintAxis: "#8b9aa3",
  grid: "rgba(139, 156, 169, 0.32)",
  zeroLine: "rgba(139, 156, 169, 0.45)",
} as const

function movingAverage(vals: number[], window = 5): (number | null)[] {
  return vals.map((_, i) => {
    const start = Math.max(0, i - window + 1)
    const slice = vals.slice(start, i + 1).filter(v => v != null) as number[]
    if (slice.length < Math.min(3, window)) return null
    return slice.reduce((s, v) => s + v, 0) / slice.length
  })
}

export function RollingBarLine({
  events,
  height = 220,
  maWindow = 5,
  trendSeries = [],
  roundSeriesByMetric,
}: {
  events: RollingEvent[]
  height?: number
  maWindow?: number
  trendSeries?: number[]
  roundSeriesByMetric?: Partial<Record<RollingTab, number[]>>
}) {
  const [tab, setTab] = useState<RollingTab>("TOTAL")
  const [view, setView] = useState<RollingView>("events")
  if (!events.length) return <ChartEmpty height={height + 32} msg="No event history" />

  const key = ROLLING_KEY[tab]
  const orderedEvents = [...events].reverse() // oldest → newest
  const perRoundForTab = tab === "TOTAL" ? trendSeries : (roundSeriesByMetric?.[tab] ?? [])

  const eventVals = orderedEvents.map((e) => {
    const v = (e as unknown as Record<string, unknown>)[key]
    return typeof v === "number" ? v : null
  })
  const roundVals = perRoundForTab.map((v) => (typeof v === "number" ? v : null))

  const coverageByTab = ROLLING_TABS.reduce(
    (acc, rollingTab) => {
      const eventKey = ROLLING_KEY[rollingTab]
      const eventCoverage = orderedEvents.filter((e) => {
        const v = (e as unknown as Record<string, unknown>)[eventKey]
        return typeof v === "number"
      }).length
      const roundsCoverage = rollingTab === "TOTAL" ? trendSeries.length : (roundSeriesByMetric?.[rollingTab]?.length ?? 0)
      acc[rollingTab] = {
        eventsAvailable: eventCoverage > 0,
        roundsAvailable: roundsCoverage > 0,
      }
      return acc
    },
    {} as Record<RollingTab, { eventsAvailable: boolean; roundsAvailable: boolean }>,
  )

  const vals = view === "events" ? eventVals : roundVals
  const ma = movingAverage(vals.filter((v): v is number => typeof v === "number"), maWindow)

  // Rebuild ma aligned to full vals array (skip nulls)
  let maIdx = 0
  const maAligned = vals.map((v) => {
    if (v == null) return null
    return ma[maIdx++] ?? null
  })

  const barColors = vals.map((v) => {
    if (v == null) return "transparent"
    return heatSpectrumHexFromUnit(heatUnitForRolling(v))
  })

  const legendBarSwatch = barColors.find((c) => c !== "transparent") ?? heatSpectrumHexFromUnit(0.5)

  return (
    <div>
      <div style={{ display: "flex", gap: 4, marginBottom: 8, paddingLeft: 2, alignItems: "center", flexWrap: "wrap" }}>
        {(["events", "rounds"] as const).map((rollingView) => (
          <button
            key={rollingView}
            onClick={() => setView(rollingView)}
            style={{
              fontFamily: T.mono,
              fontSize: 9,
              fontWeight: 700,
              letterSpacing: "0.1em",
              padding: "3px 8px",
              border: `1px solid ${view === rollingView ? "var(--green-dim)" : T.border}`,
              borderRadius: 3,
              background: view === rollingView ? "var(--green-bg)" : "transparent",
              color: view === rollingView ? T.green : T.faint,
              cursor: "pointer",
              transition: "all 120ms",
            }}
          >
            {rollingView === "events" ? "EVENTS" : "ROUNDS"}
          </button>
        ))}
        {ROLLING_TABS.map((t) => {
          const availability = coverageByTab[t]
          const enabled = view === "events" ? availability.eventsAvailable : availability.roundsAvailable
          const disabledMessage =
            view === "events"
              ? `No ${t} event aggregates in stored rounds`
              : `No ${t} round series available`
          return (
            <button
              key={t}
              disabled={!enabled}
              onClick={() => setTab(t)}
              style={{
                fontFamily: T.mono,
                fontSize: 9,
                fontWeight: 700,
                letterSpacing: "0.1em",
                padding: "3px 8px",
                border: `1px solid ${tab === t ? "var(--green-dim)" : T.border}`,
                borderRadius: 3,
                background: tab === t ? "var(--green-bg)" : "transparent",
                color: tab === t ? T.green : T.faint,
                cursor: enabled ? "pointer" : "not-allowed",
                opacity: enabled ? 1 : 0.45,
                transition: "all 120ms",
              }}
              title={!enabled ? disabledMessage : undefined}
            >
              {t}
            </button>
          )
        })}
        <span style={{ marginLeft: "auto", fontFamily: T.mono, fontSize: 8, color: T.faint, alignSelf: "center" }}>
          {maWindow}-{view === "events" ? "event" : "round"} moving avg
        </span>
      </div>
      {vals.filter((v) => v != null).length === 0 ? (
        <ChartEmpty
          height={height}
          msg={view === "events" ? "No event aggregates for selected tab" : "No round series for selected tab"}
        />
      ) : (

      <ReactECharts
        style={{ height }}
        option={{
          animation: true,
          animationDuration: 400,
          grid: { top: 12, right: 16, bottom: 36, left: 44 },
          xAxis: {
            type: "category",
            data: (view === "events" ? orderedEvents : vals.map((_, idx) => ({ event_name: `R${idx + 1}` }))).map(e => {
              const n = e.event_name ?? ""
              return view === "events" ? n.split(" ").slice(0, 2).join(" ") : n
            }),
            axisLabel: { color: ROLLING_EC.faintAxis, fontSize: 8, fontFamily: T.mono, rotate: 30, interval: 0 },
            axisLine: { lineStyle: { color: ROLLING_EC.grid } },
            splitLine: { show: false },
          },
          yAxis: {
            type: "value",
            scale: true,
            axisLabel: {
              color: ROLLING_EC.muted, fontSize: 9, fontFamily: T.mono,
              formatter: (v: number) => `${v > 0 ? "+" : ""}${v.toFixed(1)}`,
            },
            splitLine: { lineStyle: { color: ROLLING_EC.grid, type: "dashed" } },
            axisLine: { show: false },
          },
          series: [
            {
              name: tab,
              type: "bar",
              data: vals.map((v, i) => ({
                value: v,
                itemStyle: { color: barColors[i], borderRadius: (v ?? 0) >= 0 ? [2, 2, 0, 0] : [0, 0, 2, 2] },
              })),
              barMaxWidth: 32,
              z: 1,
            },
            {
              name: `${maWindow}-event avg`,
              type: "line",
              data: maAligned,
              smooth: 0.4,
              showSymbol: false,
              connectNulls: true,
              lineStyle: { color: ROLLING_EC.text, width: 2 },
              itemStyle: { color: ROLLING_EC.text },
              z: 2,
            },
            // zero line
            {
              name: "_zero",
              type: "line",
              data: vals.map(() => 0),
              showSymbol: false,
              lineStyle: { color: ROLLING_EC.zeroLine, width: 1, type: "dashed" },
              z: 0,
              tooltip: { show: false },
            },
          ],
          legend: {
            data: [
              { name: tab, itemStyle: { color: legendBarSwatch } },
              { name: `${maWindow}-event avg`, itemStyle: { color: ROLLING_EC.text } },
            ],
            textStyle: { color: ROLLING_EC.muted, fontSize: 9, fontFamily: T.mono },
            top: 0, right: 0, itemHeight: 8, itemWidth: 14,
          },
          tooltip: {
            trigger: "axis",
            axisPointer: { type: "shadow" },
            ...TOOLTIP,
            formatter: (params: Array<{ seriesName?: string; value?: number; name?: string; dataIndex?: number; [k: string]: unknown }>) => {
              const bar = params.find((p) => p.seriesName === tab)
              const ma  = params.find((p) => p.seriesName !== tab && p.seriesName !== "_zero")
              const ev  = orderedEvents[bar?.dataIndex ?? 0]
              const v   = bar?.value
              const col = v != null ? heatSpectrumHexFromUnit(heatUnitForRolling(v)) : ROLLING_EC.muted
              const fin = view === "events" && ev?.fin_text ? ` <span style="color:${ROLLING_EC.muted}">· ${ev.fin_text}</span>` : ""
              const course = view === "events" && ev?.course_name ? `<br/><span style="color:${ROLLING_EC.faintAxis}">${ev.course_name}</span>` : ""
              const maLine = ma?.value != null
                ? `<br/><span style="color:${ROLLING_EC.muted}">MA: ${signed(ma.value)}</span>` : ""
              const label = view === "events" ? (ev?.event_name ?? bar?.name) : `Round ${(bar?.dataIndex ?? 0) + 1}`
              return `<b>${label}</b>${fin}${course}<br/>${tab}: <b style="color:${col}">${v != null ? signed(v) : "—"}</b>${maLine}`
            },
          },
        }}
      />
      )}
    </div>
  )
}

/* ══════════════════════════════════════════════════════════════════════
   4. APPROACH ARC GAUGES — semicircle arc per yardage bucket
   ══════════════════════════════════════════════════════════════════════ */
export type ApproachBucket = {
  label: string       // e.g. "75-100"
  fw_sg:  number      // fairway SG
  rgh_sg: number      // rough SG
  tour_avg_fw?: number  // tour average for FW (default 0)
  tour_avg_rgh?: number
}

function ArcGauge({
  value,
  tourAvg = 0,
  maxAbs = 1.5,
  label,
  sublabel,
  size = 80,
}: {
  value: number
  tourAvg?: number
  maxAbs?: number
  label: string
  sublabel?: string
  size?: number
}) {
  const cx = size / 2, cy = size * 0.62
  const r  = size * 0.38

  // Arc spans 180° (π radians), starting at left (π) going to right (0/2π)
  const toAngle = (v: number) => Math.PI - ((v + maxAbs) / (maxAbs * 2)) * Math.PI

  const startA = Math.PI
  const endA   = 0
  const valA   = toAngle(Math.min(maxAbs, Math.max(-maxAbs, value)))
  const avgA   = toAngle(Math.min(maxAbs, Math.max(-maxAbs, tourAvg)))

  const polar = (a: number, rad: number) => ({
    x: cx + rad * Math.cos(a),
    y: cy - rad * Math.sin(a),
  })

  // Track arc (full semicircle)
  const tStart = polar(startA, r), tEnd = polar(endA, r)
  const trackD = `M ${tStart.x} ${tStart.y} A ${r} ${r} 0 0 1 ${tEnd.x} ${tEnd.y}`

  // Value arc
  const vEnd = polar(valA, r)

  // Tour avg tick
  const avgOuter = polar(avgA, r + 4)
  const avgInner = polar(avgA, r - 4)

  const col = value >= 0 ? T.green : T.red

  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 2 }}>
      <svg width={size} height={size * 0.72} viewBox={`0 0 ${size} ${size * 0.72}`}>
        {/* Track */}
        <path d={trackD} fill="none" stroke={T.border} strokeWidth={4} strokeLinecap="round" />

        {/* Fill arc */}
        <path
          d={`M ${tStart.x} ${tStart.y} A ${r} ${r} 0 0 1 ${vEnd.x} ${vEnd.y}`}
          fill="none"
          stroke={col}
          strokeWidth={4}
          strokeLinecap="round"
          opacity={0.85}
        />

        {/* Tour average tick */}
        <line x1={avgInner.x} y1={avgInner.y} x2={avgOuter.x} y2={avgOuter.y}
          stroke={T.muted} strokeWidth={1.5} />

        {/* Value text */}
        <text x={cx} y={cy - 4} textAnchor="middle" fill={col}
          fontSize={size * 0.15} fontFamily={T.mono} fontWeight={700}>
          {value > 0 ? "+" : ""}{value.toFixed(2)}
        </text>
      </svg>

      {/* Labels */}
      <div style={{ fontFamily: T.mono, fontSize: 9, fontWeight: 700, color: T.muted, letterSpacing: "0.08em", textAlign: "center" }}>
        {label}
      </div>
      {sublabel && (
        <div style={{ fontFamily: T.mono, fontSize: 8, color: T.faint, letterSpacing: "0.06em" }}>
          {sublabel}
        </div>
      )}
    </div>
  )
}

export function ApproachArcGauges({
  buckets,
}: {
  buckets: ApproachBucket[]
}) {
  const [lie, setLie] = useState<"fw" | "rgh">("fw")

  if (!buckets.length) return <ChartEmpty height={120} msg="No approach data" />

  return (
    <div>
      {/* FW / Rough toggle */}
      <div style={{ display: "flex", gap: 6, marginBottom: 12 }}>
        {(["fw", "rgh"] as const).map(l => (
          <button
            key={l}
            onClick={() => setLie(l)}
            style={{
              fontFamily: T.mono, fontSize: 9, fontWeight: 700, letterSpacing: "0.1em",
              padding: "3px 10px",
              border: `1px solid ${lie === l ? T.greenDim : T.border}`,
              borderRadius: 3,
              background: lie === l ? T.greenBg : "transparent",
              color: lie === l ? T.green : T.faint,
              cursor: "pointer", transition: "all 120ms",
            }}
          >
            {l === "fw" ? "FAIRWAY" : "ROUGH"}
          </button>
        ))}
        <span style={{ marginLeft: "auto", fontFamily: T.mono, fontSize: 8, color: T.faint, alignSelf: "center" }}>
          — = tour avg
        </span>
      </div>

      <div style={{
        display: "grid",
        gridTemplateColumns: `repeat(${Math.min(buckets.length, 6)}, 1fr)`,
        gap: "8px 4px",
      }}>
        {buckets.map((b, i) => (
          <ArcGauge
            key={i}
            value={lie === "fw" ? b.fw_sg : b.rgh_sg}
            tourAvg={lie === "fw" ? (b.tour_avg_fw ?? 0) : (b.tour_avg_rgh ?? 0)}
            label={b.label}
            sublabel={lie === "fw" ? "FW" : "Rgh"}
            size={90}
            maxAbs={1.8}
          />
        ))}
      </div>
    </div>
  )
}

/* ══════════════════════════════════════════════════════════════════════
   5. HISTORY TABLE — finish chips + inline SG mini-bars
   ══════════════════════════════════════════════════════════════════════ */
export type HistoryEvent = {
  event_name: string
  event_completed?: string | null
  course_name?: string | null
  fin_text?: string | null
  avg_score?: number | null
  avg_to_par?: number | null
  avg_sg_total?: number | null
  avg_sg_ott?:   number | null
  avg_sg_app?:   number | null
  avg_sg_arg?:   number | null
  avg_sg_putt?:  number | null
  avg_sg_t2g?:   number | null
  rounds_played?: number
}

function FinishChip({ fin }: { fin: string | null | undefined }) {
  if (!fin) return <span style={{ color: T.faint, fontFamily: T.mono, fontSize: 10 }}>—</span>
  const f = fin.trim().toUpperCase()
  const isWin = f === "1" || f === "W"
  const isCut = f.includes("CUT") || f.includes("WD") || f.includes("DQ")
  const isTop10 = !isWin && !isCut && (parseInt(f.replace("T", "")) <= 10)
  const isTop25 = !isWin && !isCut && !isTop10 && (parseInt(f.replace("T", "")) <= 25)

  let bg = T.surface, color = T.muted, border = T.border
  if (isWin)   { bg = T.goldBg; color = T.gold; border = T.goldDim }
  if (isTop10) { bg = T.greenBg; color = T.green; border = T.greenDim }
  if (isTop25) { bg = "transparent"; color = T.muted; border = T.border }
  if (isCut)   { bg = T.redBg; color = T.red; border = T.redDim }

  return (
    <span style={{
      fontFamily: T.mono, fontSize: 9, fontWeight: 700,
      padding: "2px 6px",
      background: bg, color, border: `1px solid ${border}`,
      borderRadius: 3,
      letterSpacing: "0.04em",
      whiteSpace: "nowrap",
    }}>
      {isWin ? "WIN" : f}
    </span>
  )
}

function SgMiniBar({ value, maxAbs = 2.5 }: { value: number | null | undefined; maxAbs?: number }) {
  if (value == null) return <span style={{ color: T.faint, fontFamily: T.mono, fontSize: 9 }}>—</span>
  const pct = Math.min(100, Math.abs(value) / maxAbs * 50) // 50% = max half
  const col = value >= 0 ? T.green : T.red
  const isPos = value >= 0

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
      <div style={{ width: 44, height: 6, background: T.border, borderRadius: 2, position: "relative", flexShrink: 0 }}>
        {/* center tick */}
        <div style={{ position: "absolute", left: "50%", top: 0, width: 1, height: 6, background: T.faint }} />
        {/* bar */}
        <div style={{
          position: "absolute",
          top: 0, height: 6,
          left: isPos ? "50%" : `${50 - pct}%`,
          width: `${pct}%`,
          background: col,
          borderRadius: 2,
          opacity: 0.85,
        }} />
      </div>
      <span style={{
        fontFamily: T.mono, fontSize: 9, fontWeight: 600,
        color: col, letterSpacing: "-0.01em", minWidth: 38,
        textAlign: "right",
      }}>
        {value > 0 ? "+" : ""}{value.toFixed(2)}
      </span>
    </div>
  )
}

export function HistoryTable({
  events,
  maxRows = 16,
}: {
  events: HistoryEvent[]
  maxRows?: number
}) {
  const [expanded, setExpanded] = useState(false)
  const rows = expanded ? events : events.slice(0, maxRows)

  if (!events.length) return <ChartEmpty height={80} msg="No tournament history" />

  return (
    <div>
      <div style={{ overflow: "auto" }}>
        <table style={{
          width: "100%", borderCollapse: "collapse",
          fontFamily: T.mono, fontSize: 10,
        }}>
          <thead>
            <tr style={{ borderBottom: `1px solid ${T.border}` }}>
              {["EVENT", "DATE", "COURSE", "RDS", "FIN", "TOTAL", "OTT", "APP", "ARG", "PUTT", "T2G"].map(h => (
                <th key={h} style={{
                  padding: "5px 8px", textAlign: h === "EVENT" || h === "COURSE" ? "left" : "center",
                  fontSize: 8, fontWeight: 700, letterSpacing: "0.1em",
                  color: T.faint, whiteSpace: "nowrap",
                }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((e, i) => (
              <tr key={i} style={{
                borderBottom: `1px solid ${T.divider}`,
                background: i % 2 === 0 ? "transparent" : `${T.bg1}55`,
              }}>
                <td style={{ padding: "6px 8px", color: T.text, fontWeight: 600, whiteSpace: "nowrap", maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis" }}>
                  {e.event_name}
                </td>
                <td style={{ padding: "6px 8px", color: T.faint, textAlign: "center", whiteSpace: "nowrap" }}>
                  {e.event_completed ?? "—"}
                </td>
                <td style={{ padding: "6px 8px", color: T.muted, whiteSpace: "nowrap", maxWidth: 140, overflow: "hidden", textOverflow: "ellipsis" }}>
                  {e.course_name ?? "—"}
                </td>
                <td style={{ padding: "6px 8px", color: T.muted, textAlign: "center", whiteSpace: "nowrap" }}>
                  {e.rounds_played ?? "—"}
                </td>
                <td style={{ padding: "6px 8px", textAlign: "center" }}>
                  <FinishChip fin={e.fin_text} />
                </td>
                <td style={{ padding: "6px 8px" }}>
                  <SgMiniBar value={e.avg_sg_total} maxAbs={3} />
                </td>
                <td style={{ padding: "6px 8px" }}>
                  <SgMiniBar value={e.avg_sg_ott} maxAbs={1.5} />
                </td>
                <td style={{ padding: "6px 8px" }}>
                  <SgMiniBar value={e.avg_sg_app} maxAbs={2} />
                </td>
                <td style={{ padding: "6px 8px" }}>
                  <SgMiniBar value={e.avg_sg_arg} maxAbs={1.5} />
                </td>
                <td style={{ padding: "6px 8px" }}>
                  <SgMiniBar value={e.avg_sg_putt} maxAbs={1.5} />
                </td>
                <td style={{ padding: "6px 8px" }}>
                  <SgMiniBar value={e.avg_sg_t2g} maxAbs={2.5} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {events.length > maxRows && (
        <button
          onClick={() => setExpanded(e => !e)}
          style={{
            marginTop: 8, fontFamily: T.mono, fontSize: 9, letterSpacing: "0.08em",
            padding: "4px 12px", border: `1px solid ${T.border}`, borderRadius: 3,
            background: "transparent", color: T.muted, cursor: "pointer",
            transition: "color 120ms",
          }}
        >
          {expanded ? "SHOW LESS" : `SHOW ALL ${events.length}`}
        </button>
      )}
    </div>
  )
}
