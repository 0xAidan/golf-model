/**
 * course-guide.tsx
 * Hole-by-hole course guide component.
 *
 * Features:
 *  - 18-hole selector nav (numbered tabs)
 *  - Per-hole stat block (Par, Yds, HCP, Avg, Delta, Diff rank)
 *  - Procedural SVG overhead hole map (fairway, green, bunkers, water)
 *  - Editorial footnote per hole
 *  - Optional player performance overlay (their avg vs field avg)
 */

import { useState } from "react"
import type { CourseData, HoleData } from "@/lib/course-data"

/* ── Design tokens ───────────────────────────────────────────────────── */
const T = {
  bg:      "#080a0b",
  bg1:     "#0d1012",
  bg2:     "#111416",
  surface: "#141719",
  border:  "#1f2426",
  divider: "#161a1c",
  text:    "#e8ecef",
  muted:   "#6b7a84",
  faint:   "#374349",
  green:   "#22c55e",
  gold:    "#f5b418",
  red:     "#ef4444",
  mono:    "'JetBrains Mono', 'Fira Code', monospace",
}

/* ═══════════════════════════════════════════════════════════════════════
   SVG HOLE MAP — static asset loader
   Augusta: real hand-traced SVGs from golfcourse.wiki (dark-themed)
   Other courses: per-hole procedural SVGs (hole-specific shapes)
   ═══════════════════════════════════════════════════════════════════════ */

function HoleSvg({ hole, courseKey }: { hole: HoleData; courseKey: string }) {
  const src = `/course-svgs/${courseKey}/hole_${hole.number}.svg`
  return (
    <div
      style={{
        width: "100%",
        aspectRatio: "200/340",
        background: "#0a1a0a",
        borderRadius: 4,
        overflow: "hidden",
        display: "flex",
        alignItems: "stretch",
      }}
      aria-label={`Overhead diagram of hole ${hole.number}${hole.name ? ` — ${hole.name}` : ""}`}
    >
      <img
        src={src}
        alt={`Hole ${hole.number} layout`}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "contain",
          display: "block",
        }}
        onError={(e) => {
          // Fallback: hide broken image
          (e.target as HTMLImageElement).style.display = "none"
        }}
      />
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════════════
   HOLE STATS BLOCK
   ═══════════════════════════════════════════════════════════════════════ */
function HoleStats({
  hole,
  playerAvg,
}: {
  hole: HoleData
  playerAvg?: number | null
}) {
  const delta = hole.scoring_avg - hole.par
  const deltaSgn = delta > 0 ? "+" : ""
  const diffColor = hole.diff_rank <= 3 ? T.red : hole.diff_rank >= 16 ? T.green : T.muted

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {/* Hole name + number */}
      <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
        <span style={{ fontFamily: T.mono, fontSize: 22, fontWeight: 800, color: T.text, letterSpacing: "-0.03em" }}>
          {hole.number}
        </span>
        {hole.name && (
          <span style={{ fontFamily: T.mono, fontSize: 11, fontWeight: 600, color: T.green, letterSpacing: "0.06em", textTransform: "uppercase" }}>
            {hole.name}
          </span>
        )}
      </div>

      {/* Stat grid */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "8px 4px" }}>
        {[
          { label: "Par",  value: hole.par.toString(),    color: T.text },
          { label: "Yards", value: hole.yards.toLocaleString(), color: T.text },
          { label: "HCP",  value: `#${hole.hcp}`,         color: T.muted },
          { label: "Avg",  value: hole.scoring_avg.toFixed(2), color: delta > 0.3 ? T.red : delta < 0 ? T.green : T.text },
          { label: "Δ Par", value: `${deltaSgn}${delta.toFixed(2)}`, color: delta > 0 ? T.red : T.green },
          { label: "Diff", value: `#${hole.diff_rank}/18`, color: diffColor },
        ].map(s => (
          <div key={s.label} style={{ display: "flex", flexDirection: "column", gap: 1 }}>
            <span style={{ fontFamily: T.mono, fontSize: 7, fontWeight: 600, letterSpacing: "0.12em", textTransform: "uppercase", color: T.faint }}>
              {s.label}
            </span>
            <span style={{ fontFamily: T.mono, fontSize: 13, fontWeight: 700, color: s.color, letterSpacing: "-0.02em" }}>
              {s.value}
            </span>
          </div>
        ))}
      </div>

      {/* Player overlay */}
      {playerAvg != null && (
        <div style={{
          display: "flex", alignItems: "center", gap: 8,
          padding: "6px 8px",
          background: T.bg2, border: `1px solid ${T.border}`, borderRadius: 3,
        }}>
          <span style={{ fontFamily: T.mono, fontSize: 8, color: T.faint, letterSpacing: "0.1em", textTransform: "uppercase" }}>Your Avg</span>
          <span style={{ fontFamily: T.mono, fontSize: 14, fontWeight: 700, color: playerAvg <= hole.scoring_avg ? T.green : T.red }}>
            {playerAvg.toFixed(2)}
          </span>
          <span style={{ fontFamily: T.mono, fontSize: 9, color: T.muted }}>
            vs field {hole.scoring_avg.toFixed(2)}
          </span>
          <span style={{
            marginLeft: "auto",
            fontFamily: T.mono, fontSize: 9, fontWeight: 700,
            color: playerAvg <= hole.scoring_avg ? T.green : T.red,
          }}>
            {playerAvg <= hole.scoring_avg
              ? `+${(hole.scoring_avg - playerAvg).toFixed(2)} below field`
              : `${(playerAvg - hole.scoring_avg).toFixed(2)} above field`
            }
          </span>
        </div>
      )}

      {/* Hole shape badges */}
      <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
        {[
          { show: true, label: `Par ${hole.par}`, col: T.muted },
          { show: hole.shape.water === true, label: "WATER", col: "#3b82f6" },
          { show: (hole.shape.bunkers ?? 0) >= 3, label: "MULTI-BUNKER", col: T.gold },
          { show: hole.diff_rank <= 3, label: "SIGNATURE", col: T.red },
          { show: hole.par === 3, label: "PAR 3", col: T.green },
          { show: hole.par === 5, label: "PAR 5", col: T.green },
        ].filter(b => b.show).map(b => (
          <span key={b.label} style={{
            fontFamily: T.mono, fontSize: 7, fontWeight: 700, letterSpacing: "0.12em",
            padding: "2px 6px",
            border: `1px solid ${b.col}44`,
            borderRadius: 2,
            color: b.col,
            background: `${b.col}12`,
          }}>
            {b.label}
          </span>
        ))}
      </div>

      {/* Editorial note */}
      <div style={{
        fontFamily: T.mono, fontSize: 10, color: T.muted,
        lineHeight: 1.5, letterSpacing: "0.02em",
        borderLeft: `2px solid ${T.green}44`, paddingLeft: 8,
        fontStyle: "italic",
      }}>
        {hole.note}
      </div>
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════════════
   DIFFICULTY STRIP — all 18 holes overview bar
   ═══════════════════════════════════════════════════════════════════════ */
function DifficultyStrip({ holes, activeHole, onSelect }: {
  holes: HoleData[]
  activeHole: number
  onSelect: (n: number) => void
}) {
  const maxDelta = Math.max(...holes.map(h => Math.abs(h.scoring_avg - h.par)))

  return (
    <div style={{ display: "flex", gap: 2, alignItems: "flex-end", height: 40, padding: "0 2px" }}>
      {holes.map(h => {
        const delta = h.scoring_avg - h.par
        const barH = Math.max(4, Math.abs(delta) / maxDelta * 30)
        const col = delta > 0.3 ? T.red : delta < 0 ? T.green : T.muted
        const isActive = h.number === activeHole
        return (
          <div
            key={h.number}
            onClick={() => onSelect(h.number)}
            style={{
              flex: 1,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: 2,
              cursor: "pointer",
              opacity: isActive ? 1 : 0.5,
              transition: "opacity 100ms",
            }}
          >
            <div style={{
              width: "100%", height: barH,
              background: isActive ? T.green : col,
              borderRadius: "2px 2px 0 0",
            }} />
            <span style={{
              fontFamily: T.mono, fontSize: 7, fontWeight: isActive ? 700 : 400,
              color: isActive ? T.green : T.faint,
            }}>
              {h.number}
            </span>
          </div>
        )
      })}
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════════════
   COURSE GUIDE — main export
   ═══════════════════════════════════════════════════════════════════════ */
export function CourseGuide({
  course,
  playerHoleAvgs,
}: {
  course: CourseData
  /** Optional: player's average score per hole number (1-indexed) */
  playerHoleAvgs?: Record<number, number>
}) {
  const [activeHole, setActiveHole] = useState(1)
  const hole = course.holes.find(h => h.number === activeHole) ?? course.holes[0]
  const playerAvg = playerHoleAvgs?.[activeHole] ?? null

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {/* Course header */}
      <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
        <span style={{ fontFamily: T.mono, fontSize: 13, fontWeight: 700, color: T.text }}>
          {course.name}
        </span>
        <span style={{ fontFamily: T.mono, fontSize: 10, color: T.muted }}>{course.location}</span>
        <span style={{ marginLeft: "auto", fontFamily: T.mono, fontSize: 9, color: T.faint }}>
          Par {course.par} · {course.yards.toLocaleString()} yds
        </span>
      </div>

      {/* Difficulty strip */}
      <DifficultyStrip holes={course.holes} activeHole={activeHole} onSelect={setActiveHole} />

      {/* Hole number selector */}
      <div style={{ display: "flex", gap: 3, flexWrap: "wrap" }}>
        {course.holes.map(h => {
          const isActive = h.number === activeHole
          const delta = h.scoring_avg - h.par
          const dotCol = delta > 0.3 ? T.red : delta < 0 ? T.green : T.faint
          return (
            <button
              key={h.number}
              onClick={() => setActiveHole(h.number)}
              style={{
                fontFamily: T.mono,
                fontSize: 9,
                fontWeight: 700,
                width: 28,
                height: 28,
                border: `1px solid ${isActive ? `${T.green}55` : T.border}`,
                borderRadius: 3,
                background: isActive ? `${T.green}18` : "transparent",
                color: isActive ? T.green : T.muted,
                cursor: "pointer",
                transition: "all 100ms",
                position: "relative",
              }}
            >
              {h.number}
              {/* Par dot indicator */}
              <span style={{
                position: "absolute",
                bottom: 2, right: 2,
                width: 3, height: 3,
                borderRadius: "50%",
                background: dotCol,
                display: "block",
              }} />
            </button>
          )
        })}
      </div>

      {/* Main hole panel */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "1fr 1fr",
        gap: 12,
        background: T.bg1,
        border: `1px solid ${T.border}`,
        borderRadius: 4,
        padding: 14,
      }}>
        {/* Left: stats */}
        <HoleStats hole={hole} playerAvg={playerAvg} />

        {/* Right: SVG map */}
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <span style={{ fontFamily: T.mono, fontSize: 8, fontWeight: 600, letterSpacing: "0.12em", textTransform: "uppercase", color: T.faint }}>
            Hole Layout
          </span>
          <div style={{
            background: "#0a1a0a",
            border: `1px solid ${T.border}`,
            borderRadius: 3,
            overflow: "hidden",
          }}>
            <HoleSvg hole={hole} courseKey={course.course_key} />
          </div>
        </div>
      </div>

      {/* Course notes */}
      {course.notes && (
        <div style={{
          fontFamily: T.mono, fontSize: 9, color: T.faint,
          letterSpacing: "0.02em", lineHeight: 1.5,
        }}>
          {course.notes}
        </div>
      )}
    </div>
  )
}
