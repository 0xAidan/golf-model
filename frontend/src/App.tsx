import { lazy, Suspense, useState } from "react"
import { Navigate, useLocation } from "react-router-dom"

const LearningWorkspace = lazy(() => import("@/features/learning-workspace/learning-workspace").then(module => ({default: module.LearningWorkspace})))

const SharedCardPage = lazy(() => import("@/features/matchup-desk/shared-card-page"))

const LegacyApp = lazy(() => import("@/app/legacy-app"))
const LegacyToaster = lazy(() => import("sonner").then(module => ({ default: module.Toaster })))

export default function App() {
  const location = useLocation()
  const deskRoute = ["/", "/rankings", "/markets", "/models", "/performance", "/card", "/evidence"].includes(location.pathname)
  const previewRoute = location.pathname === "/preview" || location.pathname.startsWith("/preview/")
  const sharedRoute = location.pathname === "/shared-card"
  const legacyRoute = !deskRoute && !previewRoute && !sharedRoute
  const [hasOpenedLegacy, setHasOpenedLegacy] = useState(legacyRoute)

  if (legacyRoute && !hasOpenedLegacy) setHasOpenedLegacy(true)

  return <>
    {deskRoute ? <Suspense fallback={<main className="matchup-desk"><p style={{padding:32}} role="status">Opening Golf Model…</p></main>}><LearningWorkspace /></Suspense>
      : sharedRoute ? <Suspense fallback={<main className="matchup-desk"><p style={{padding:32}} role="status">Opening shared picks…</p></main>}><SharedCardPage /></Suspense>
      : previewRoute ? <Navigate to="/" replace />
      : <Suspense fallback={<div className="matchup-desk"><p style={{padding:32}} role="status">Loading research tools…</p></div>}><LegacyApp/></Suspense>}
    {/* Only legacy tools emit toasts. Retain the host after first use so pending notifications survive navigation. */}
    {(legacyRoute || hasOpenedLegacy) && <Suspense fallback={null}><LegacyToaster position="top-center" richColors closeButton /></Suspense>}
  </>
}
