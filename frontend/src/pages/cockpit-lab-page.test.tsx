import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it, vi, beforeEach } from "vitest"

import { CockpitLabPage } from "@/pages/cockpit-lab-page"
import type { PredictionWorkspacePageProps } from "@/pages/prediction-workspace-page"

vi.mock("@/pages/prediction-workspace-page", () => ({
  PredictionWorkspacePage: () => <div data-testid="cockpit-stub">Cockpit stub</div>,
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

describe("CockpitLabPage", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("renders streak-safety banner and research deck headings", async () => {
    renderLab()

    expect(screen.getByTestId("cockpit-lab-banner")).toHaveTextContent(/lab_live_tournament/i)
    expect(screen.getByTestId("cockpit-lab-banner")).toHaveTextContent(/lab_profile_enabled/i)
    expect(screen.getByTestId("cockpit-stub")).toBeInTheDocument()

    expect(await screen.findByText(/research instrumentation/i)).toBeInTheDocument()
    expect(screen.getByText(/calibration \(by market\)/i)).toBeInTheDocument()
    expect(screen.getByText(/clv by book/i)).toBeInTheDocument()
    expect(screen.getByText(/ab report \(v5 vs legacy\)/i)).toBeInTheDocument()
    expect(screen.getByText(/shadow monte carlo/i)).toBeInTheDocument()
  })

  it("shows AB empty-state copy when no source_event_id for tab", async () => {
    renderLab({
      liveSnapshot: {},
      predictionTab: "past",
    })

    expect(await screen.findByText(/source_event_id/i)).toBeInTheDocument()
    expect(apiMock.getResearchAbReport).not.toHaveBeenCalled()
  })

  it("shows partial-lab warning when only one lab section is populated", async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <CockpitLabPage
            cockpitWorkspaceProps={buildMinimalCockpitProps()}
            usingProdSnapshotFallback={false}
            labLanePartialSections
          />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    expect(screen.getByTestId("cockpit-lab-partial-sections-banner")).toHaveTextContent(
      /partial lab snapshot/i,
    )
  })
})
