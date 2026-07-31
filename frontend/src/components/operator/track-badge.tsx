export function TrackBadge({ track }: { track: "champion" | "challenger" }) {
  const challenger = track === "challenger"
  return (
    <span className={`inline-flex border px-2 py-1 text-xs font-semibold uppercase tracking-[0.12em] ${challenger ? "border-amber-400/40 bg-amber-400/10 text-amber-100" : "border-emerald-400/35 bg-emerald-400/10 text-emerald-100"}`}>
      {challenger ? "Challenger" : "Champion"}
    </span>
  )
}
