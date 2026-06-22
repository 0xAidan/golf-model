import type { CompareEventOption } from "@/components/compare/compare-types"

export function CompareEventSelector({
  options,
  value,
  onChange,
  disabled,
}: {
  options: CompareEventOption[]
  value: string
  onChange: (eventId: string) => void
  disabled?: boolean
}) {
  return (
    <label className="flex min-w-[220px] flex-1 flex-col gap-1 sm:max-w-md">
      <span className="text-xs font-medium uppercase tracking-wide text-[var(--text-secondary)]">
        Tournament
      </span>
      <select
        className="compare-event-select rounded border border-[var(--border)] bg-[var(--bg-1)] px-3 py-2 text-sm text-[var(--text-primary)]"
        value={value}
        disabled={disabled}
        data-testid="compare-event-select"
        aria-label="Select tournament to compare"
        onChange={(event) => onChange(event.target.value)}
      >
        {options.map((option) => (
          <option key={option.eventId} value={option.eventId}>
            {option.mode === "current" ? option.label : `${option.label}${option.hasGrading ? "" : " (board only)"}`}
          </option>
        ))}
      </select>
    </label>
  )
}
