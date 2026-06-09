import { useMemo } from "react"

import { HistoryTable, RollingBarLine } from "@/components/charts-v2"
import type { HistoryEvent, RollingEvent } from "@/components/charts-v2"
import { ModelCommandSection } from "@/components/product"
import { HeroDataGrid } from "@/components/monitoring"
import {
  buildCourseFitColumns,
  buildRecentRoundsColumns,
  type CourseFitRow,
} from "@/lib/players-columns"
import type { StandalonePlayerProfile, StandaloneRecentRoundSample } from "@/lib/types"

export const FormHistorySection = ({ standalone }: { standalone: StandalonePlayerProfile }) => {
  const roundsOldestToNewest = useMemo(
    () => [...(standalone.recent_rounds_sample ?? [])].reverse(),
    [standalone.recent_rounds_sample],
  )

  const roundSeriesByMetric = useMemo(() => {
    const pick = (key: keyof StandaloneRecentRoundSample) =>
      roundsOldestToNewest
        .map((round) => round[key])
        .filter((value): value is number => typeof value === "number")
    return {
      APP: pick("sg_app"),
      ARG: pick("sg_arg"),
      PUTT: pick("sg_putt"),
      OTT: pick("sg_ott"),
      T2G: pick("sg_t2g"),
    } as const
  }, [roundsOldestToNewest])

  const courseFitRows = useMemo(
    (): CourseFitRow[] => standalone.course_summaries ?? [],
    [standalone.course_summaries],
  )

  const recentRoundRows = useMemo(
    () => standalone.recent_rounds_sample?.slice(0, 24) ?? [],
    [standalone.recent_rounds_sample],
  )

  const courseColumns = useMemo(() => buildCourseFitColumns(), [])
  const roundColumns = useMemo(() => buildRecentRoundsColumns(), [])

  return (
    <>
      {standalone.recent_events.length > 0 ? (
        <ModelCommandSection
          id="players-event-form"
          title="Event form"
          description="Per-event SG bars with moving average and round-level tabs"
          testId="players-section-event-form"
        >
          <RollingBarLine
            events={standalone.recent_events as RollingEvent[]}
            height={220}
            maWindow={5}
            trendSeries={standalone.trend_series}
            roundSeriesByMetric={roundSeriesByMetric}
          />
        </ModelCommandSection>
      ) : null}

      {standalone.recent_events.length > 0 ? (
        <ModelCommandSection
          id="players-tournament-history"
          title="Tournament history"
          description="Finish chips and inline SG bars"
          testId="players-section-tournament-history"
        >
          <HistoryTable events={standalone.recent_events as HistoryEvent[]} maxRows={16} />
        </ModelCommandSection>
      ) : null}

      {courseFitRows.length > 0 ? (
        <ModelCommandSection
          id="players-course-rollups"
          title="Course rollups"
          description="Most tracked courses by rounds played"
          testId="players-section-course-rollups"
        >
          <HeroDataGrid
            data={courseFitRows}
            columns={courseColumns}
            density="compact"
            getRowId={(row) => row.course_name}
            testId="players-profile-course-rollups-grid"
          />
        </ModelCommandSection>
      ) : null}

      {recentRoundRows.length > 0 ? (
        <ModelCommandSection
          id="players-round-log"
          title="Round log"
          description="Recent rounds with SG splits"
          testId="players-section-round-log"
        >
          <HeroDataGrid
            data={recentRoundRows}
            columns={roundColumns}
            density="compact"
            getRowId={(row) =>
              `${row.event_completed ?? "na"}-${row.round_num ?? "r"}-${row.event_name ?? ""}`
            }
            testId="players-profile-round-log-grid"
          />
        </ModelCommandSection>
      ) : null}
    </>
  )
}
