import { useState } from "react"

import { AppContent } from "@/app/app-content"
import { InteractionProvider } from "@/providers/interaction-provider"
import { LiveSnapshotProvider } from "@/providers/live-snapshot-provider"

export default function App() {
  const [manualRefreshPending, setManualRefreshPending] = useState(false)
  const [uiAlert, setUiAlert] = useState<string | null>(null)

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
