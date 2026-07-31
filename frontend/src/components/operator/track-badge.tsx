export function TrackBadge({ track }: { track: "champion" | "challenger" }) {
  const challenger = track === "challenger"
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] ${
        challenger
          ? "border-[rgba(192,132,252,0.4)] bg-[rgba(192,132,252,0.1)] text-[#d8b4fe]"
          : "border-[rgba(52,211,153,0.4)] bg-[rgba(52,211,153,0.1)] text-[var(--op-accent)]"
      }`}
    >
      <span className={`op-dot ${challenger ? "bg-[#c084fc]" : "bg-[var(--op-accent)]"}`} aria-hidden="true" />
      {challenger ? "Challenger" : "Champion"}
    </span>
  )
}
