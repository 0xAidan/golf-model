import { Suspense, useState } from "react"
import { useLocation } from "react-router-dom"

import { AppContent } from "@/app/app-content"
import { lazyWithRetry } from "@/lib/lazy-import"
import { CalmModeProvider } from "@/providers/calm-mode-provider"
import { InteractionProvider } from "@/providers/interaction-provider"
import { LiveSnapshotProvider } from "@/providers/live-snapshot-provider"

const OperatorRoutes = lazyWithRetry(() =>
  import("@/app/operator/operator-routes").then((mod) => ({ default: mod.OperatorRoutes })),
)

const PreviewFallback = () => (
  <div data-testid="operator-preview-fallback">Loading operator preview…</div>
)

export default function App() {
  const location = useLocation()
  const [manualRefreshPending, setManualRefreshPending] = useState(false)
  const [uiAlert, setUiAlert] = useState<string | null>(null)

  if (location.pathname === "/preview" || location.pathname.startsWith("/preview/")) {
    return (
      <Suspense fallback={<PreviewFallback />}>
        <OperatorRoutes />
      </Suspense>
    )
  }

  return (
    <CalmModeProvider>
      <InteractionProvider>
        <LiveSnapshotProvider manualRefreshPending={manualRefreshPending} uiAlert={uiAlert}>
          <AppContent
            manualRefreshPending={manualRefreshPending}
            setManualRefreshPending={setManualRefreshPending}
            setUiAlert={setUiAlert}
          />
        </LiveSnapshotProvider>
      </InteractionProvider>
    </CalmModeProvider>
  )
}
