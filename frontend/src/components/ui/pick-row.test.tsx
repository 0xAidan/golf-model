import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { PickRow } from "@/components/ui/pick-row"
import type { MatchupBet } from "@/lib/types"

const sampleBet: MatchupBet = {
  pick: "Scottie Scheffler",
  pick_key: "scheffler",
  opponent: "Rory McIlroy",
  opponent_key: "mcilroy",
  odds: "+120",
  book: "draftkings",
  model_win_prob: 0.55,
  implied_prob: 0.45,
  ev: 0.08,
  ev_pct: "8.0%",
  composite_gap: 1.2,
  form_gap: 0.3,
  course_fit_gap: 0.4,
  reason: "Model edge on course fit.",
  tier: "GOOD",
}

describe("PickRow", () => {
  it("renders pick anatomy fields", () => {
    render(<PickRow bet={sampleBet} />)
    expect(screen.getByTestId("pick-row")).toHaveAttribute("data-tier", "GOOD")
    expect(screen.getByText("Scottie Scheffler")).toBeInTheDocument()
    expect(screen.getByText("Rory McIlroy")).toBeInTheDocument()
    expect(screen.getByText("72-hole")).toBeInTheDocument()
  })

  it("expands detail on button click", async () => {
    const user = userEvent.setup()
    const onExpand = vi.fn()
    render(<PickRow bet={sampleBet} onExpand={onExpand} />)
    await user.click(screen.getByRole("button", { name: "Detail" }))
    expect(onExpand).toHaveBeenCalledOnce()
  })
})
