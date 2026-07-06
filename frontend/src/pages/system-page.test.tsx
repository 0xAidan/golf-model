import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { SystemPage } from "@/pages/system-page"
import type { DataHealthReport } from "@/lib/types"

const { apiMock, toastMock } = vi.hoisted(() => ({
  apiMock: {
    getOpsHealth: vi.fn(),
    getDataHealth: vi.fn(),
    getLatestOpsJob: vi.fn(),
    requestWorkerRestart: vi.fn(),
  },
  toastMock: {
    message: vi.fn(),
    error: vi.fn(),
  },
}))

vi.mock("@/lib/api", () => ({
  api: apiMock,
}))

vi.mock("sonner", () => ({
  toast: toastMock,
}))

vi.mock("@/components/cockpit/event-modules", () => ({
  DiagnosticsGradingPanel: () => <div data-testid="diagnostics-grading-panel-stub">Diagnostics panel</div>,
}))

function buildDataHealth(overrides: Partial<DataHealthReport> = {}): DataHealthReport {
  return {
    status: "green",
    summary: "Storage looks healthy.",
    file_sizes_human: { main: "12 GB", wal: "10 MB" },
    latest_backup: { name: "golf_model_20260706.db", size_mb: 1200, integrity: { ok: true } },
    storage_warnings: [],
    ...overrides,
  }
}

function renderSystemPage({
  opsHealth,
  dataHealth,
  latestJob,
}: {
  opsHealth?: Record<string, unknown>
  dataHealth?: DataHealthReport
  latestJob?: Record<string, unknown> | null
} = {}) {
  apiMock.getOpsHealth.mockResolvedValue({
    ok: true,
    summary: "healthy",
    grading: {
      status: "ok",
      events_with_ungraded_positive_ev: 0,
      last_auto_grade_status: "complete",
    },
    live_refresh: {
      running: true,
      heartbeat_age_seconds: 42,
      snapshot_age_seconds: 90,
    },
    ...opsHealth,
  })
  apiMock.getDataHealth.mockResolvedValue(dataHealth ?? buildDataHealth())
  apiMock.getLatestOpsJob.mockResolvedValue({ job: latestJob ?? null })
  apiMock.requestWorkerRestart.mockResolvedValue({
    ok: true,
    status: "accepted",
    message: "Worker restart requested.",
  })

  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <SystemPage
          dashboard={{ ai_status: { available: false } }}
          liveSnapshot={{ upcoming_tournament: { event_name: "John Deere Classic" } }}
          predictionTab="upcoming"
          isLiveActive={false}
          gradingHistory={[]}
          predictionRun={null}
          secondaryBets={[]}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe("SystemPage", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("renders the healthy system summary and four status panels", async () => {
    renderSystemPage()

    await waitFor(() => {
      expect(screen.getByTestId("system-overall-status")).toHaveTextContent(
        /all four core systems are healthy/i,
      )
    })
    expect(screen.getByTestId("system-worker-panel")).toHaveTextContent(/worker/i)
    expect(screen.getByTestId("system-grading-panel")).toHaveTextContent(/grading reconciliation is clear/i)
    expect(screen.getByTestId("system-storage-panel")).toHaveTextContent(/database, backups, and archives look healthy/i)
    expect(screen.getByTestId("system-jobs-panel")).toHaveTextContent(/no recent grade job is recorded yet/i)
  })

  it("shows worker trouble and requests a restart from the page", async () => {
    const user = userEvent.setup()

    renderSystemPage({
      opsHealth: {
        ok: false,
        live_refresh: {
          running: false,
          heartbeat_age_seconds: 4200,
          snapshot_age_seconds: 4800,
        },
      },
    })

    expect(await screen.findByTestId("system-worker-panel")).toHaveTextContent(/worker is down/i)

    await user.click(screen.getByRole("button", { name: /restart worker/i }))

    await waitFor(() => {
      expect(apiMock.requestWorkerRestart).toHaveBeenCalledWith({ requested_by: "system-page" })
    })
  })

  it("surfaces storage risk when data health is red", async () => {
    renderSystemPage({
      dataHealth: buildDataHealth({
        status: "red",
        summary: "Disk is near full.",
        storage_warnings: ["Disk free space is below the hard floor."],
      }),
    })

    await waitFor(() => {
      expect(screen.getByTestId("system-storage-panel")).toHaveTextContent(
        /storage health is in a red state/i,
      )
    })
  })

  it("surfaces grading gaps in the grading panel", async () => {
    renderSystemPage({
      opsHealth: {
        grading: {
          status: "partial",
          events_with_ungraded_positive_ev: 2,
          last_auto_grade_status: "partial",
        },
      },
    })

    await waitFor(() => {
      expect(screen.getByTestId("system-grading-panel")).toHaveTextContent(
        /2 completed events still have ungraded \+EV picks/i,
      )
    })
  })
})
