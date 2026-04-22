import { CockpitModule } from "./workspace"

/**
 * Team-event notice rendered in place of the normal bettable-card modules
 * (matchups, placement value, 3-balls) when the active tournament is a
 * two-player team event (currently only the Zurich Classic of New Orleans
 * on the PGA Tour — Foursomes + Fourball).
 *
 * The backend pipeline intentionally short-circuits on these events; see
 * `src/event_format.py` and `GolfModelService.run_analysis`. The frontend
 * mirrors the skip by surfacing this explanation rather than an empty card,
 * so the dashboard never looks broken during team-event weeks.
 *
 * Pair / team matchup modelling is a tracked follow-up; until it lands, no
 * placement or matchup output is emitted or displayed for these events.
 */
export function TeamEventNotice({
  eventName,
  courseName,
  mode,
}: {
  eventName?: string | null
  courseName?: string | null
  mode: "live" | "upcoming"
}) {
  const title =
    mode === "upcoming" ? "Team event — no bettable card this week" : "Team event in progress — cards suspended"

  return (
    <CockpitModule
      title={title}
      description={eventName ? `${eventName}${courseName ? ` · ${courseName}` : ""}` : undefined}
      tone="muted"
    >
      <div
        data-testid="team-event-notice"
        style={{
          display: "flex",
          flexDirection: "column",
          gap: 12,
          padding: "8px 2px",
          fontSize: 13,
          lineHeight: 1.5,
          color: "var(--fg-muted, #cbd5e1)",
        }}
      >
        <p style={{ margin: 0 }}>
          This tournament is played as a two-player team event
          <strong> (Foursomes + Fourball)</strong>. Our composite model,
          placement markets, and individual head-to-head matchup pricing all
          assume individual stroke play, so they do not apply here.
        </p>

        <div
          role="table"
          aria-label="Output status for this event"
          style={{
            display: "grid",
            gridTemplateColumns: "1fr auto",
            rowGap: 4,
            columnGap: 12,
            fontSize: 12,
            borderTop: "1px solid var(--border, rgba(148,163,184,0.2))",
            paddingTop: 8,
          }}
        >
          <Row label="Placement value bets (Top 5/10/20, Outright)" status="skipped" />
          <Row label="Individual head-to-head matchups" status="skipped" />
          <Row label="3-ball value" status="skipped" />
          <Row label="Pair / team matchups" status="not_modelled" />
          <Row label="Individual composite rankings" status="reference_only" />
        </div>

        <p style={{ margin: 0, fontSize: 12, color: "var(--fg-subtle, #94a3b8)" }}>
          The regular individual-format pipeline resumes automatically at the next non-team event.
        </p>
      </div>
    </CockpitModule>
  )
}

function Row({
  label,
  status,
}: {
  label: string
  status: "skipped" | "not_modelled" | "reference_only"
}) {
  const statusMeta: Record<typeof status, { text: string; color: string }> = {
    skipped: { text: "Skipped", color: "#f87171" },
    not_modelled: { text: "Not yet modelled", color: "#fbbf24" },
    reference_only: { text: "Reference only", color: "#60a5fa" },
  }
  const meta = statusMeta[status]
  return (
    <>
      <span style={{ minWidth: 0 }}>{label}</span>
      <span style={{ color: meta.color, fontWeight: 500, whiteSpace: "nowrap" }}>{meta.text}</span>
    </>
  )
}

