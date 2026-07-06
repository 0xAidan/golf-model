import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it, vi, beforeEach } from "vitest"

import { CockpitLabPage } from "@/pages/cockpit-lab-page"
import type { PredictionWorkspacePageProps } from "@/pages/prediction-workspace-page"
import {
  LAB_RESEARCH_INSTRUMENTATION_EXPANDED_KEY,
} from "@/lib/lab-research-instrumentation-storage"

const LEGACY_LAB_RESEARCH_INSTRUMENTATION_EXPANDED_KEY =
  "golf-model:cockpit-lab-research-instrumentation-expanded"

vi.mock("@/pages/prediction-workspace-page", () => ({
  PredictionWorkspacePage: () => <div data-testid="lab-board-workspace-stub">Dashboard workspace stub</div>,
}))

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    getCalibrationByMarket: vi.fn(async () => ({
      bet_types: ["matchup"],
      curves: {
        matchup: [
          {
            probability_bucket: "0.5-0.55",
            predicted_avg: 0.52,
            actual_hit_rate: 0.51,
            sample_size: 10,
            correction_factor: 1.0,
          },
        ],
      },
      min_sample_for_correction: 30,
    })),
    getClvSummary: vi.fn(async () => ({
      overall: { n_bets: 0, avg_clv_pct: null, significant: false },
      by_book: [],
      min_bets_for_significance: 50,
    })),
    getResearchAbReport: vi.fn(async () => ({
      ok: true,
      event_id: "evt1",
      counts: { raw_rows: 1, paired_keys: 0 },
      paired_metrics: {},
      paired_samples: [],
    })),
  },
}))

vi.mock("@/lib/api", () => ({
  api: apiMock,
}))

function buildMinimalCockpitProps(
  overrides: Partial<PredictionWorkspacePageProps> = {},
): PredictionWorkspacePageProps {
  return {
    liveSnapshot: {
      upcoming_tournament: { source_event_id: "evt1", event_name: "Test" },
    },
    runtimeStatus: { label: "Live", tone: "good" },
    snapshotNotice: null,
    snapshotAgeSeconds: 1,
    predictionTab: "upcoming",
    onPredictionTabChange: vi.fn(),
    availableBooks: [],
    selectedBooks: [],
    onSelectedBooksChange: vi.fn(),
    matchupSearch: "",
    onMatchupSearchChange: vi.fn(),
    minEdge: 0.02,
    onMinEdgeChange: vi.fn(),
    filteredMatchups: [],
    gradingHistory: [],
    players: [],
    predictionRun: null,
    selectedPlayerKey: "",
    onPlayerSelect: vi.fn(),
    playerProfileState: "unavailable",
    onPlayerProfileRetry: vi.fn(),
    richProfilesEnabled: false,
    secondaryBets: [],
    ...overrides,
  }
}

function renderLab(overrides?: Partial<PredictionWorkspacePageProps>) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <CockpitLabPage cockpitWorkspaceProps={buildMinimalCockpitProps(overrides)} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe("LabBoardPage (CockpitLabPage)", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.removeItem(LAB_RESEARCH_INSTRUMENTATION_EXPANDED_KEY)
    window.localStorage.removeItem(LEGACY_LAB_RESEARCH_INSTRUMENTATION_EXPANDED_KEY)
  })

  it("renders lab header and collapsible research deck (expand to see cards)", async () => {
    const user = userEvent.setup()
    renderLab()

    expect(screen.getByTestId("lab-board-banner-wrap")).toHaveTextContent(/lab_live_tournament/i)
    expect(screen.getByTestId("lab-board-lane-stripe")).toBeInTheDocument()
    expect(screen.getByTestId("lab-board-secondary-chip")).toHaveTextContent(/validation pending/i)
    expect(screen.getByTestId("lab-board-workspace-stub")).toBeInTheDocument()
    expect(screen.getByTestId("lab-board-instrumentation-section")).toBeInTheDocument()
    expect(screen.queryByTestId("lab-board-banner")).not.toBeInTheDocument()
    expect(screen.queryByTestId("lab-board-partial-sections-banner")).not.toBeInTheDocument()
    expect(screen.queryByTestId("lab-board-research-pane")).not.toBeInTheDocument()
    expect(screen.getByTestId("lab-board-research-toggle")).toHaveTextContent(/research instrumentation/i)
    expect(screen.queryByText(/calibration \(by market\)/i)).not.toBeInTheDocument()

    await user.click(screen.getByTestId("lab-board-research-toggle"))

    expect(await screen.findByText(/calibration \(by market\)/i)).toBeInTheDocument()
    expect(screen.getByText(/clv by book/i)).toBeInTheDocument()
    expect(screen.getByText(/ab report \(v5 vs legacy\)/i)).toBeInTheDocument()
    expect(screen.getByText(/shadow monte carlo/i)).toBeInTheDocument()
  })

  it("shows AB empty-state copy when no source_event_id for tab", async () => {
    const user = userEvent.setup()
    renderLab({
      liveSnapshot: {},
      predictionTab: "past",
    })

    await user.click(screen.getByTestId("lab-board-research-toggle"))
    expect(await screen.findByText(/source_event_id/i)).toBeInTheDocument()
    expect(apiMock.getResearchAbReport).not.toHaveBeenCalled()
  })

  it("does not render duplicate external partial-lab banner (workspace owns lane trust)", () => {
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter>
          <CockpitLabPage
            cockpitWorkspaceProps={buildMinimalCockpitProps()}
            usingProdSnapshotFallback={false}
            labLanePartialSections
          />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    expect(screen.queryByTestId("lab-board-partial-sections-banner")).not.toBeInTheDocument()
    expect(screen.queryByTestId("lab-board-prod-fallback-banner")).not.toBeInTheDocument()
  })
})
