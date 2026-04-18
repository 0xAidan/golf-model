import { useEffect } from "react"

import { api } from "@/lib/api"

type LiveRefreshSettings = {
  enabled?: boolean
  autostart?: boolean
  tour?: string
}

type LiveRefreshStatus = {
  status?: {
    running?: boolean
  }
  settings?: LiveRefreshSettings
}

type EnsureLiveRefreshRuntimeDeps = {
  getLiveRefreshStatus: () => Promise<LiveRefreshStatus>
  patchAutoresearchSettings: (payload: { live_refresh: LiveRefreshSettings }) => Promise<unknown>
  startLiveRefresh: (payload: { tour: string; live_refresh: LiveRefreshSettings }) => Promise<unknown>
}

const DEFAULT_DEPS: EnsureLiveRefreshRuntimeDeps = {
  getLiveRefreshStatus: api.getLiveRefreshStatus,
  patchAutoresearchSettings: api.patchAutoresearchSettings,
  startLiveRefresh: api.startLiveRefresh,
}

export async function ensureLiveRefreshRuntime({
  requestedTour,
  deps = DEFAULT_DEPS,
}: {
  requestedTour?: string
  deps?: EnsureLiveRefreshRuntimeDeps
}) {
  const runtime = await deps.getLiveRefreshStatus()
  const settings = runtime.settings ?? {}

  if (settings.enabled === false) {
    return
  }

  const tour = settings.tour || requestedTour || "pga"
  const liveRefresh = { ...settings, enabled: true, autostart: true, tour }

  if (settings.autostart !== true) {
    await deps.patchAutoresearchSettings({
      live_refresh: liveRefresh,
    })
  }

  if (!runtime.status?.running) {
    await deps.startLiveRefresh({
      tour,
      live_refresh: liveRefresh,
    })
  }
}

export function useLiveRefreshRuntime({
  requestedTour,
  onError,
}: {
  requestedTour?: string
  onError: (message: string) => void
}) {
  useEffect(() => {
    let isCancelled = false

    const run = async () => {
      try {
        await ensureLiveRefreshRuntime({ requestedTour })
      } catch {
        if (!isCancelled) {
          onError("Could not verify live runtime automatically. Use 'Check runtime' and inspect status.")
        }
      }
    }

    void run()

    return () => {
      isCancelled = true
    }
  }, [onError, requestedTour])
}
