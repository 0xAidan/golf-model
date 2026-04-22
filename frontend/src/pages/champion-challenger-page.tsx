import { useQuery } from "@tanstack/react-query"

import { api } from "@/lib/api"
import type { ChampionChallengerSummary, ChampionChallengerModelSummary } from "@/lib/types"

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

  return (
    <div
      style={{ flex: 1, overflowY: "auto", padding: "16px 18px", fontFamily: "var(--font-mono)" }}
      data-testid="champion-challenger-page"
    >
      <div style={{ marginBottom: 16 }}>
        <div
          style={{
            fontSize: 11,
            fontWeight: 700,
            letterSpacing: "0.14em",
            textTransform: "uppercase",
            color: "var(--text-muted)",
          }}
        >
          Research · Champion / Challenger
        </div>
        <div style={{ fontSize: 10, color: "var(--text-faint)", marginTop: 4 }}>
          Shadow-mode evaluation. Challengers never price live bets. Trailing 14-day and 30-day
          Brier, matchup ROI, and CLV.
        </div>
      </div>

      {summaryQuery.isLoading && (
        <div style={{ fontSize: 11, color: "var(--text-faint)" }}>Loading…</div>
      )}
      {summaryQuery.isError && (
        <div
          data-testid="champion-challenger-error"
          style={{ fontSize: 11, color: "var(--text-muted)" }}
        >
          Failed to load summary.
        </div>
      )}

      {data && (
        <div>
          <div style={{ fontSize: 10, color: "var(--text-faint)", marginBottom: 8 }}>
            Champion: <strong>{data.champion}</strong>
            {data.challengers.length > 0 ? (
              <>
                {" · "}Challengers: {data.challengers.join(", ")}
              </>
            ) : (
              <> · No active challengers</>
            )}
          </div>
          <table
            data-testid="champion-challenger-table"
            style={{
              width: "100%",
              borderCollapse: "collapse",
              fontSize: 11,
            }}
          >
            <thead>
              <tr style={{ textAlign: "left", color: "var(--text-muted)" }}>
                <th style={{ padding: "6px 8px" }}>Model</th>
                <th style={{ padding: "6px 8px" }}>Brier (30d)</th>
                <th style={{ padding: "6px 8px" }}>N</th>
                <th style={{ padding: "6px 8px" }}>Matchup ROI 14d</th>
                <th style={{ padding: "6px 8px" }}>Matchup ROI 30d</th>
                <th style={{ padding: "6px 8px" }}>CLV 30d</th>
              </tr>
            </thead>
            <tbody>
              {data.models.map((model) => {
                const win30 = modelWindow(model, "30")
                const win14 = modelWindow(model, "14")
                return (
                  <tr
                    key={model.model_name}
                    data-testid={`champion-challenger-row-${model.model_name}`}
                    style={{ borderTop: "1px solid var(--border-muted, #2a2a2a)" }}
                  >
                    <td style={{ padding: "6px 8px" }}>{model.model_name}</td>
                    <td style={{ padding: "6px 8px" }}>{formatNumber(win30?.brier?.brier)}</td>
                    <td style={{ padding: "6px 8px" }}>{win30?.brier?.n ?? 0}</td>
                    <td style={{ padding: "6px 8px" }}>
                      {formatPct(win14?.matchup_roi?.roi_pct)}
                    </td>
                    <td style={{ padding: "6px 8px" }}>
                      {formatPct(win30?.matchup_roi?.roi_pct)}
                    </td>
                    <td style={{ padding: "6px 8px" }}>{formatBps(win30?.clv?.clv_bps)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
