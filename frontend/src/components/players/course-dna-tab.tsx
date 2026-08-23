import { useQuery } from "@tanstack/react-query"

import { Stagger, StaggerItem } from "@/components/motion/primitives"
import { SkeletonPanelRows } from "@/components/motion/skeletons"
import { api } from "@/lib/api"
import { getHeatScale, readCssVar } from "@/lib/chart-theme"

/**
 * CourseDnaTab — explains WHY the fit score is what it is:
 * course importance weights vs player SG strengths, plus a
 * hole-by-hole heat grid when hole data exists (honest empty
 * state otherwise).
 */
export function CourseDnaTab({
  playerKey,
  courseId,
}: {
  playerKey: string
  courseId?: string | null
}) {
  const dna = useQuery({
    queryKey: ["redesign-course-dna", playerKey, courseId ?? null],
    queryFn: () => api.redesign.courseDna(playerKey, courseId),
    staleTime: 120_000,
  })
  const holes = useQuery({
    queryKey: ["redesign-hole-heat", playerKey, courseId ?? null],
    queryFn: () => api.redesign.holeHeat(playerKey, courseId),
    staleTime: 300_000,
  })

  if (dna.isLoading) {
    return (
      <div className="panel p-5" data-testid="course-dna-loading">
        <SkeletonPanelRows rows={4} />
      </div>
    )
  }

  const course = dna.data?.course ?? null

  return (
    <Stagger className="flex flex-col gap-4">
      {course ? (
        <StaggerItem>
          <div className="panel">
            <div className="panel__header">
              <span className="panel__title">Course profile — {course.course_name}</span>
              {dna.data?.has_course_profile ? (
                <span className="chip">Encyclopedia</span>
              ) : (
                <span className="chip" title="Derived from round history only">
                  Derived
                </span>
              )}
            </div>
            <div className="panel__body">
              <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm text-[var(--text-secondary)]">
                {course.yardage ? <span>{course.yardage} yds</span> : null}
                {course.par ? <span>Par {course.par}</span> : null}
                {course.grass_type_greens ? <span>Greens: {course.grass_type_greens}</span> : null}
                {course.grass_type_fairway ? <span>Fairways: {course.grass_type_fairway}</span> : null}
                {course.green_speed ? <span>Green speed: {course.green_speed}</span> : null}
                {course.fairway_width ? <span>Width: {course.fairway_width}</span> : null}
              </div>

              {(course.sg_ott_importance != null ||
                course.sg_app_importance != null ||
                course.sg_arg_importance != null ||
                course.sg_putt_importance != null) ? (
                <ImportanceBars course={course} sgWindows={dna.data?.player_sg_windows ?? []} />
              ) : null}
            </div>
          </div>
        </StaggerItem>
      ) : (
        <StaggerItem>
          <div className="panel p-5 text-sm text-[var(--text-muted)]" data-testid="course-dna-empty">
            No course profile is available for this context yet.
          </div>
        </StaggerItem>
      )}

      <StaggerItem>
        {holes.isLoading ? (
          <div className="panel p-5">
            <SkeletonPanelRows rows={3} />
          </div>
        ) : holes.data?.available ? (
          <HoleHeatGrid holes={holes.data.holes} />
        ) : (
          <div className="panel p-5 text-sm text-[var(--text-muted)]" data-testid="hole-heat-empty">
            {holes.data?.note ?? "Hole-level history has not been ingested for this player yet."}
          </div>
        )}
      </StaggerItem>
    </Stagger>
  )
}

function ImportanceBars({
  course,
  sgWindows,
}: {
  course: NonNullable<import("@/lib/types").PlayerCourseDna["course"]>
  sgWindows: import("@/lib/types").SgWindowValue[]
}) {
  // Latest window per category (rows arrive newest-first).
  const latest = new Map<string, number>()
  for (const row of sgWindows) {
    if (row.metric_value == null) continue
    if (!latest.has(row.metric_name)) latest.set(row.metric_name, row.metric_value)
  }

  const rows = [
    { key: "sg_ott", label: "Off the tee", importance: course.sg_ott_importance },
    { key: "sg_app", label: "Approach", importance: course.sg_app_importance },
    { key: "sg_arg", label: "Around the green", importance: course.sg_arg_importance },
    { key: "sg_putt", label: "Putting", importance: course.sg_putt_importance },
  ].filter((row) => row.importance != null)

  if (rows.length === 0) return null

  return (
    <div className="mt-4 flex flex-col gap-3" data-testid="course-dna-importance">
      <div className="text-[11px] font-medium uppercase tracking-wide text-[var(--text-muted)]">
        What this course rewards vs this player's strength
      </div>
      {rows.map((row) => {
        const playerValue = latest.get(row.key)
        const heat = getHeatScale()
        const strong = (playerValue ?? 0) > 0.35
        const weak = (playerValue ?? 0) < -0.35
        return (
          <div key={row.key} className="grid grid-cols-[10rem_1fr_1fr] items-center gap-3 text-xs">
            <span className="text-[var(--text-secondary)]">{row.label}</span>
            <div className="flex items-center gap-2">
              <span className="w-16 text-right font-mono text-[var(--text-faint)]" title="Course importance weight">
                W {row.importance!.toFixed(2)}
              </span>
              <div className="h-1.5 flex-1 rounded-full bg-[color-mix(in_srgb,var(--text-faint)_12%,transparent)]">
                <div
                  className="h-full rounded-full bg-[var(--chart-c3)]"
                  style={{ width: `${Math.min(100, Math.abs(row.importance!) * 140)}%` }}
                />
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-16 text-right font-mono text-[var(--text-faint)]" title="Player SG (latest window)">
                {playerValue != null ? `${playerValue > 0 ? "+" : ""}${playerValue.toFixed(2)}` : "—"}
              </span>
              <div className="h-1.5 flex-1 rounded-full bg-[color-mix(in_srgb,var(--text-faint)_12%,transparent)]">
                <div
                  className="h-full rounded-full"
                  style={{
                    width: playerValue != null ? `${Math.min(100, Math.abs(playerValue) * 60)}%` : "0%",
                    background: strong ? heat.posStrong : weak ? heat.negStrong : readCssVar("--chart-c2", "#60a5fa"),
                  }}
                />
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

function HoleHeatGrid({ holes }: { holes: import("@/lib/types").HoleHeatCell[] }) {
  const heat = getHeatScale()

  const cellColor = (cell: import("@/lib/types").HoleHeatCell): string => {
    const net = (cell.birdie_pct ?? 0) - (cell.bogey_pct ?? 0)
    if (net > 0.06) return heat.posStrong
    if (net > 0.02) return heat.pos
    if (net < -0.06) return heat.negStrong
    if (net < -0.02) return heat.neg
    return heat.neutral
  }

  return (
    <div className="panel">
      <div className="panel__header">
        <span className="panel__title">Hole-by-hole history</span>
        <span className="text-[10px] text-[var(--text-faint)]">green = gains · red = bleeds</span>
      </div>
      <div className="panel__body grid grid-cols-6 gap-2 sm:grid-cols-9 md:grid-cols-12" data-testid="hole-heat-grid">
        {holes.map((cell) => (
          <div
            key={cell.hole_num}
            className="flex flex-col items-center gap-1 rounded-lg border border-[var(--border)] px-1 py-2"
            style={{ background: `color-mix(in srgb, ${cellColor(cell)} 22%, transparent)` }}
            title={`Hole ${cell.hole_num} · ${cell.rounds_played} rounds · avg ${cell.avg_score_to_par?.toFixed(2) ?? "—"} to par`}
          >
            <span className="num text-sm font-bold text-[var(--text)]">{cell.hole_num}</span>
            <span className="num text-[10px] text-[var(--text-muted)]">
              {cell.birdie_pct != null ? `${(cell.birdie_pct * 100).toFixed(0)}%` : "—"}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
