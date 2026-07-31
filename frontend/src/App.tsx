import { useState } from "react"
import { useLocation } from "react-router-dom"

import { AppContent } from "@/app/app-content"
import { OperatorRoutes } from "@/app/operator/operator-routes"
import { InteractionProvider } from "@/providers/interaction-provider"
import { LiveSnapshotProvider } from "@/providers/live-snapshot-provider"

export default function App() {
  const location = useLocation()
  const [manualRefreshPending, setManualRefreshPending] = useState(false)
  const [uiAlert, setUiAlert] = useState<string | null>(null)

  if (location.pathname === "/preview" || location.pathname.startsWith("/preview/")) {
    return <OperatorRoutes />
  }

  return (
    <InteractionProvider>
      <LiveSnapshotProvider manualRefreshPending={manualRefreshPending} uiAlert={uiAlert}>
        <AppContent
          manualRefreshPending={manualRefreshPending}
          setManualRefreshPending={setManualRefreshPending}
          setUiAlert={setUiAlert}
        />
      </LiveSnapshotProvider>
    </InteractionProvider>
  )
}
