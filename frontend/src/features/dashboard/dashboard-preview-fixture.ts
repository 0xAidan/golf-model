import type { PickRowData } from "@/components/operator/pick-row"

export const dashboardPreviewFixture = {
  event: { name: "Rocket Classic", course: "Detroit Golf Club", updated: "10:42 ET" },
  picks: [
    { id: "matsuyama-morikawa", player: "Hideki Matsuyama", opponent: "Collin Morikawa", market: "72-hole matchup", edge: "+7.8%", odds: "-110" },
    { id: "young-theegala", player: "Cameron Young", opponent: "Sahith Theegala", market: "72-hole matchup", edge: "+6.2%", odds: "-105" },
    { id: "bhatia-rai", player: "Akshay Bhatia", opponent: "Aaron Rai", market: "72-hole matchup", edge: "+5.4%", odds: "+100" },
  ] satisfies PickRowData[],
  rankings: [
    { id: "matsuyama", player: "Hideki Matsuyama", rank: 1, score: "88.4", trend: "+2" },
    { id: "morikawa", player: "Collin Morikawa", rank: 2, score: "87.2", trend: "—" },
    { id: "young", player: "Cameron Young", rank: 3, score: "85.8", trend: "+1" },
  ],
} as const
