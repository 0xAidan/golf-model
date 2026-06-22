import { CollapsibleSection } from "@/components/ui/collapsible-section"
import type { LiveTournamentSnapshot } from "@/lib/types"

function DiagnosticsCard({
  label,
  section,
}: {
  label: string
  section: LiveTournamentSnapshot | null | undefined
}) {
  const diag = section?.diagnostics
  if (!section) {
    return (
      <div className="rounded border border-[var(--border)] p-3 text-sm text-[var(--text-faint)]">
        {label}: no data
      </div>
    )
  }
  const selection = diag?.selection_counts
  const reasonCodes = diag?.reason_codes ?? {}
  const reasonEntries = Object.entries(reasonCodes).slice(0, 6)

  return (
    <div
      className="rounded border border-[var(--border)] bg-[var(--surface)] p-3 text-sm"
      data-testid={`compare-diagnostics-${label.toLowerCase().replace(/\s+/g, "-")}`}
    >
      <div className="mb-2 font-medium text-[var(--text-primary)]">{label}</div>
      <dl className="grid gap-1 text-[var(--text-secondary)]">
        <div>
          <dt className="inline text-[var(--text-faint)]">State: </dt>
          <dd className="inline">{diag?.state ?? "—"}</dd>
        </div>
        <div>
          <dt className="inline text-[var(--text-faint)]">Adaptation: </dt>
          <dd className="inline">{diag?.adaptation_state ?? "—"}</dd>
        </div>
        {selection ? (
          <div>
            <dt className="inline text-[var(--text-faint)]">Selected / input: </dt>
            <dd className="inline num">
              {selection.selected_rows ?? "—"} / {selection.input_rows ?? "—"}
            </dd>
          </div>
        ) : null}
        <div>
          <dt className="inline text-[var(--text-faint)]">Books w/ edges: </dt>
          <dd className="inline">
            {(diag?.books_with_qualifying_edges ?? []).join(", ") || "—"}
          </dd>
        </div>
        {reasonEntries.length > 0 ? (
          <div>
            <dt className="text-[var(--text-faint)]">Reason codes</dt>
            <dd className="mt-1 font-mono text-xs">
              {reasonEntries.map(([code, count]) => (
                <span key={code} className="mr-2">
                  {code}:{count}
                </span>
              ))}
            </dd>
          </div>
        ) : null}
        {(diag?.errors ?? []).length > 0 ? (
          <div className="text-[var(--red)]">
            {(diag?.errors ?? []).slice(0, 2).join(" · ")}
          </div>
        ) : null}
      </dl>
    </div>
  )
}

export function CompareDiagnosticsPanel({
  champion,
  challenger,
}: {
  champion: LiveTournamentSnapshot | undefined
  challenger: LiveTournamentSnapshot | null | undefined
}) {
  return (
    <CollapsibleSection
      title="Pipeline diagnostics"
      description="Side-by-side market pipeline state for each track"
      defaultOpen={false}
      testId="compare-diagnostics-panel"
    >
      <div className="grid gap-3 md:grid-cols-2">
        <DiagnosticsCard label="Champion" section={champion} />
        <DiagnosticsCard label="Challenger" section={challenger} />
      </div>
    </CollapsibleSection>
  )
}
