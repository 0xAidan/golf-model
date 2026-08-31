import { useState } from "react"
import { Navigate, useLocation } from "react-router-dom"

import { AppContent } from "@/app/app-content"
import { CalmModeProvider } from "@/providers/calm-mode-provider"
import { InteractionProvider } from "@/providers/interaction-provider"
import { LiveSnapshotProvider } from "@/providers/live-snapshot-provider"
import { PlayerIdentityProvider } from "@/providers/player-identity-provider"

export default function App() {
  const location = useLocation()
  const [manualRefreshPending, setManualRefreshPending] = useState(false)
  const [uiAlert, setUiAlert] = useState<string | null>(null)

  if (location.pathname === "/preview" || location.pathname.startsWith("/preview/")) {
    return <Navigate to="/" replace />
  }

  return (
    <CalmModeProvider>
      <InteractionProvider>
        <LiveSnapshotProvider manualRefreshPending={manualRefreshPending} uiAlert={uiAlert}>
          <PlayerIdentityProvider>
            <AppContent
              manualRefreshPending={manualRefreshPending}
              setManualRefreshPending={setManualRefreshPending}
              setUiAlert={setUiAlert}
            />
          </PlayerIdentityProvider>
        </LiveSnapshotProvider>
      </InteractionProvider>
    </CalmModeProvider>
  )
}
