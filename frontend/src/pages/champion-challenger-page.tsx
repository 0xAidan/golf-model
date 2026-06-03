import { useMemo } from "react"
import { useQuery } from "@tanstack/react-query"
import type { ColumnDef } from "@tanstack/react-table"

import { ProDataGrid } from "@/components/ui/pro-data-grid"
import { PageHeader } from "@/components/ui/page-header"
import { Skeleton } from "@/components/ui/skeleton"
import { api } from "@/lib/api"
import { CHAMPION_TABLE_TOOLTIPS } from "@/lib/metric-tooltips"
import type { ChampionChallengerModelSummary, ChampionChallengerSummary } from "@/lib/types"

function formatNumber(value: number | null | undefined, digits = 3): string {
  if (value === null || value === undefined) return "—"
  return value.toFixed(digits)
}

function formatPct(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—"
  return `${value.toFixed(2)}%`
}

function formatBps(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—"
  return `${value.toFixed(1)} bps`
}

function modelWindow(model: ChampionChallengerModelSummary, days: string) {
  return model.windows?.[days]
}

export function ChampionChallengerPage() {
  const summaryQuery = useQuery({
    queryKey: ["champion-challenger-summary"],
    queryFn: api.getChampionChallengerSummary,
    refetchInterval: 60_000,
  })

  const data: ChampionChallengerSummary | undefined = summaryQuery.data

  const columns = useMemo<ColumnDef<ChampionChallengerModelSummary>[]>(
    () => [
      {
        accessorKey: "model_name",
        header: "Model",
        meta: { align: "left" },
      },
      {
        id: "brier30",
        header: "Brier (30d)",
        meta: { align: "right" },
        cell: ({ row }) => formatNumber(modelWindow(row.original, "30")?.brier?.brier),
      },
      {
        id: "n",
        header: "N",
        meta: { align: "right" },
        cell: ({ row }) => modelWindow(row.original, "30")?.brier?.n ?? 0,
      },
      {
        id: "roi14",
        header: "ROI 14d",
        meta: { align: "right" },
        cell: ({ row }) => formatPct(modelWindow(row.original, "14")?.matchup_roi?.roi_pct),
      },
      {
        id: "roi30",
        header: "ROI 30d",
        meta: { align: "right" },
        cell: ({ row }) => formatPct(modelWindow(row.original, "30")?.matchup_roi?.roi_pct),
      },
      {
        id: "clv30",
        header: "CLV 30d",
        meta: { align: "right" },
        cell: ({ row }) => formatBps(modelWindow(row.original, "30")?.clv?.clv_bps),
      },
    ],
    [],
  )

  const columnVisibility = useMemo(
    () => ({
      n: false,
    }),
    [],
  )

  return (
    <div className="research-page" data-testid="champion-challenger-page">
      <PageHeader
        eyebrow="Research"
        title="Champion / Challenger"
        description="Shadow-mode evaluation. Challengers never price live bets. Trailing Brier, matchup ROI, and CLV."
      />

      {summaryQuery.isLoading && (
        <div className="research-page-loading" aria-busy="true">
          <Skeleton className="h-8 w-full max-w-md" />
          <Skeleton className="h-48 w-full" />
        </div>
      )}

      {summaryQuery.isError && (
        <p className="research-page-error" data-testid="champion-challenger-error">
          Failed to load summary.
        </p>
      )}

      {data && (
        <div className="research-page-body">
          <p className="research-page-meta">
            Champion: <strong>{data.champion}</strong>
            {data.challengers.length > 0 ? (
              <>
                {" · "}Challengers: {data.challengers.join(", ")}
              </>
            ) : (
              <> · No active challengers</>
            )}
          </p>
          <ProDataGrid
            data={data.models}
            columns={columns}
            columnVisibility={columnVisibility}
            testId="champion-challenger-table"
            getRowTestId={(row) => `champion-challenger-row-${row.model_name}`}
            emptyMessage="No models in summary"
          />
        </div>
      )}
    </div>
  )
}
