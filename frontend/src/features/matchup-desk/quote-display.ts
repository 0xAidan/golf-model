export function quoteDate(value: string | null | undefined) {
  if (!value || Number.isNaN(Date.parse(value))) return "Time unavailable"
  if (!/(Z|[+-]\d{2}:?\d{2})$/i.test(value)) return `${value} (timezone unspecified)`
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short" }).format(new Date(value))
}
export const bookLabel = (value: string) => ({ draftkings: "DraftKings", fanduel: "FanDuel", bovada: "Bovada", skybet: "Sky Bet", betmgm: "BetMGM", pinnacle: "Pinnacle" })[value.toLowerCase()] || value || "Book unavailable"
