import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { FieldBoardPanel } from "@/components/players/field-board-panel"

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    getFieldBoard: vi.fn(async () => ({
      section: "upcoming",
      event_name: "RBC",
      tournament_id: 42,
      lab_available: true,
      player_count: 2,
      players: [
        {
          player_key: "a",
          player: "Player A",
          champion_rank: 1,
          challenger_rank: 5,
          rank_delta: -4,
          composite: 80,
          course_fit: 1,
          form: 2,
          momentum: 0.1,
          matchup_count: 1,
          in_positive_ev: true,
          has_sg: false,
        },
        {
          player_key: "b",
          player: "Player B",
          champion_rank: 2,
          challenger_rank: 1,
          rank_delta: 1,
          composite: 78,
          course_fit: 0,
          form: 1,
          momentum: 0,
          matchup_count: 0,
          in_positive_ev: false,
          has_sg: false,
        },
      ],
    })),
  },
}))

vi.mock("@/lib/api", () => ({ api: apiMock }))

function renderPanel(onSelect = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <FieldBoardPanel onSelect={onSelect} />
    </QueryClientProvider>,
  )
  return onSelect
}

describe("FieldBoardPanel", () => {
  it("renders every entrant with both-track ranks and selects on row click", async () => {
    const onSelect = renderPanel()
    await waitFor(() => expect(screen.getByTestId("field-board-row-a")).toBeInTheDocument())
    expect(screen.getByTestId("field-board-row-b")).toBeInTheDocument()
    expect(screen.getByTestId("field-board-panel")).toHaveTextContent("champion vs challenger")

    fireEvent.click(screen.getByTestId("field-board-row-a"))
    expect(onSelect).toHaveBeenCalledWith("a", "Player A")
  })
})
