import type { PickRowData } from "@/components/operator/pick-row"

export type RankingRow = {
  id: string
  player: string
  rank: number
  score: string
  trend: number
  form: string
}

export const dashboardPreviewFixture = {
  event: {
    name: "Rocket Classic",
    course: "Detroit Golf Club",
    updated: "10:42 ET",
    round: "Round 2 · Friday",
    purse: "$9.6M",
  },
  summary: {
    qualifyingPicks: 6,
    bestEdge: "+7.8%",
    avgEdge: "+5.9%",
    playersRanked: 156,
  },
  picks: [
    { id: "matsuyama-morikawa", player: "Hideki Matsuyama", opponent: "Collin Morikawa", market: "72-hole matchup", edge: "+7.8%", edgeValue: 7.8, odds: "-110", winProb: "58%" },
    { id: "young-theegala", player: "Cameron Young", opponent: "Sahith Theegala", market: "72-hole matchup", edge: "+6.2%", edgeValue: 6.2, odds: "-105", winProb: "55%" },
    { id: "bhatia-rai", player: "Akshay Bhatia", opponent: "Aaron Rai", market: "72-hole matchup", edge: "+5.4%", edgeValue: 5.4, odds: "+100", winProb: "53%" },
    { id: "fitzpatrick-hovland", player: "Matt Fitzpatrick", opponent: "Viktor Hovland", market: "72-hole matchup", edge: "+5.1%", edgeValue: 5.1, odds: "-102", winProb: "52%" },
    { id: "kim-conners", player: "Tom Kim", opponent: "Corey Conners", market: "72-hole matchup", edge: "+4.6%", edgeValue: 4.6, odds: "+108", winProb: "51%" },
    { id: "clark-eckroat", player: "Wyndham Clark", opponent: "Austin Eckroat", market: "72-hole matchup", edge: "+4.1%", edgeValue: 4.1, odds: "-115", winProb: "51%" },
  ] satisfies PickRowData[],
  rankings: [
    { id: "matsuyama", player: "Hideki Matsuyama", rank: 1, score: "88.4", trend: 2, form: "T4 · T9 · 2" },
    { id: "morikawa", player: "Collin Morikawa", rank: 2, score: "87.2", trend: 0, form: "T6 · 3 · T11" },
    { id: "young", player: "Cameron Young", rank: 3, score: "85.8", trend: 1, form: "T2 · T15 · 8" },
    { id: "fitzpatrick", player: "Matt Fitzpatrick", rank: 4, score: "84.9", trend: 3, form: "T8 · T5 · T20" },
    { id: "hovland", player: "Viktor Hovland", rank: 5, score: "84.1", trend: -2, form: "T18 · T7 · MC" },
    { id: "theegala", player: "Sahith Theegala", rank: 6, score: "83.6", trend: -1, form: "T12 · T10 · T6" },
    { id: "bhatia", player: "Akshay Bhatia", rank: 7, score: "82.9", trend: 4, form: "3 · T22 · T14" },
    { id: "conners", player: "Corey Conners", rank: 8, score: "82.2", trend: 0, form: "T9 · T13 · T19" },
  ] satisfies RankingRow[],
} as const
