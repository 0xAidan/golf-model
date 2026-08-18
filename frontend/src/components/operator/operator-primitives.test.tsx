import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, test } from "vitest"

import { Drawer } from "@/components/operator/drawer"
import { FeedbackState } from "@/components/operator/feedback-state"
import { PickRow } from "@/components/operator/pick-row"
import { StatusBanner } from "@/components/operator/status-banner"

describe("operator UI primitives", () => {
  test("renders one coherent refreshing message while retaining data", () => {
    render(<StatusBanner state="refreshing" message="Refreshing lines; current picks remain visible." />)

    expect(screen.getByText("Refreshing")).toBeVisible()
    expect(screen.getByText("Refreshing lines; current picks remain visible.")).toBeVisible()
  })

  test("keeps pick names readable instead of clipping them", () => {
    render(
      <PickRow
        pick={{
          id: "matsu",
          player: "Hideki Matsuyama",
          opponent: "Collin Morikawa",
          market: "72-hole matchup",
          edge: "+7.8%",
          odds: "-110",
        }}
      />,
    )

    const row = screen.getByRole("button", { name: /Hideki Matsuyama versus Collin Morikawa/i })
    expect(row).toHaveTextContent("Hideki Matsuyama")
    expect(row).toHaveTextContent("over Collin Morikawa")
    expect(row.querySelector(".truncate")).toBeNull()
  })

  test("makes an error state actionable", () => {
    render(<FeedbackState state="error" title="Data request failed" actionLabel="Retry" onAction={() => undefined} />)

    expect(screen.getByRole("button", { name: "Retry" })).toBeVisible()
  })

  test("moves focus into an opened drawer and restores it on close", async () => {
    const user = userEvent.setup()
    render(
      <>
        <button type="button">Open details</button>
        <Drawer open title="Pick details" onClose={() => undefined}>
          <p>Jordan Spieth</p>
        </Drawer>
      </>,
    )

    expect(screen.getByRole("dialog", { name: "Pick details" })).toHaveFocus()
    await user.keyboard("{Escape}")
  })
})
