import { describe, expect, it, vi } from "vitest"

import { ensureLiveRefreshRuntime } from "@/hooks/use-live-refresh-runtime"

describe("ensureLiveRefreshRuntime", () => {
  it("patches autostart and starts the runtime when needed", async () => {
    const deps = {
      getLiveRefreshStatus: vi.fn().mockResolvedValue({
        status: { running: false },
        settings: { enabled: true, autostart: false, tour: "pga" },
      }),
      patchAutoresearchSettings: vi.fn().mockResolvedValue({}),
      startLiveRefresh: vi.fn().mockResolvedValue({}),
    }

    await ensureLiveRefreshRuntime({
      requestedTour: "pga",
      deps,
    })

    expect(deps.patchAutoresearchSettings).toHaveBeenCalledWith({
      live_refresh: { enabled: true, autostart: true, tour: "pga" },
    })
    expect(deps.startLiveRefresh).toHaveBeenCalledWith({
      tour: "pga",
      live_refresh: { enabled: true, autostart: true, tour: "pga" },
    })
  })

  it("does nothing when the runtime is explicitly disabled", async () => {
    const deps = {
      getLiveRefreshStatus: vi.fn().mockResolvedValue({
        status: { running: false },
        settings: { enabled: false, autostart: false, tour: "pga" },
      }),
      patchAutoresearchSettings: vi.fn().mockResolvedValue({}),
      startLiveRefresh: vi.fn().mockResolvedValue({}),
    }

    await ensureLiveRefreshRuntime({
      requestedTour: "pga",
      deps,
    })

    expect(deps.patchAutoresearchSettings).not.toHaveBeenCalled()
    expect(deps.startLiveRefresh).not.toHaveBeenCalled()
  })

  it("reuses an already healthy runtime without unnecessary patching", async () => {
    const deps = {
      getLiveRefreshStatus: vi.fn().mockResolvedValue({
        status: { running: true },
        settings: { enabled: true, autostart: true, tour: "pga" },
      }),
      patchAutoresearchSettings: vi.fn().mockResolvedValue({}),
      startLiveRefresh: vi.fn().mockResolvedValue({}),
    }

    await ensureLiveRefreshRuntime({
      requestedTour: "pga",
      deps,
    })

    expect(deps.patchAutoresearchSettings).not.toHaveBeenCalled()
    expect(deps.startLiveRefresh).not.toHaveBeenCalled()
  })
})
